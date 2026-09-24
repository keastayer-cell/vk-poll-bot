from __future__ import annotations

import asyncio
import json
import logging
import secrets
from dataclasses import dataclass
from typing import Any, AsyncIterator

import httpx


class VkApiError(RuntimeError):
    def __init__(self, method: str, error: dict):
        self.method = method
        self.code = int(error.get("error_code", 0))
        self.error = error
        super().__init__(
            f"VK API {method}: [{self.code}] {error.get('error_msg', 'unknown error')}"
        )


@dataclass(frozen=True)
class LongPollServer:
    server: str
    key: str
    ts: str


@dataclass(frozen=True)
class SentMessage:
    message_id: int = 0
    conversation_message_id: int = 0
    random_id: int = 0


class VkApiClient:
    def __init__(
        self,
        token: str,
        group_id: int,
        api_version: str = "5.199",
        *,
        client: httpx.AsyncClient | None = None,
    ):
        self.token = token
        self.group_id = group_id
        self.api_version = api_version
        self.client = client or httpx.AsyncClient(timeout=35.0)
        self._owns_client = client is None

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()

    async def call(self, method: str, **params: Any) -> Any:
        request_params = {key: value for key, value in params.items() if value is not None}
        request_params.update({"access_token": self.token, "v": self.api_version})
        response = await self.client.post(
            f"https://api.vk.com/method/{method}",
            data=request_params,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise VkApiError(method, payload["error"])
        return payload.get("response")

    async def get_long_poll_server(self) -> LongPollServer:
        response = await self.call("groups.getLongPollServer", group_id=self.group_id)
        return LongPollServer(
            server=str(response["server"]),
            key=str(response["key"]),
            ts=str(response["ts"]),
        )

    async def send_message(
        self, peer_id: int, text: str, keyboard: str | None = None
    ) -> SentMessage:
        random_id = secrets.randbelow(2_147_483_647) + 1
        response = await self.call(
            "messages.send",
            peer_ids=str(peer_id),
            random_id=random_id,
            message=text,
            keyboard=keyboard,
            group_id=self.group_id,
        )
        if isinstance(response, list):
            response = response[0] if response else {}
        if isinstance(response, dict):
            return SentMessage(
                message_id=int(response.get("message_id", 0)),
                conversation_message_id=int(response.get("conversation_message_id", 0)),
                random_id=random_id,
            )
        return SentMessage(message_id=int(response), random_id=random_id)

    async def edit_message(
        self,
        peer_id: int,
        text: str,
        keyboard: str | None = None,
        *,
        message_id: int = 0,
        conversation_message_id: int = 0,
    ) -> None:
        cmid = 0 if message_id else conversation_message_id
        await self.call(
            "messages.edit",
            peer_id=peer_id,
            message_id=message_id or None,
            cmid=cmid or None,
            message=text,
            keyboard=keyboard,
            group_id=self.group_id,
        )

    async def pin_message(
        self,
        peer_id: int,
        *,
        message_id: int = 0,
        conversation_message_id: int = 0,
    ) -> None:
        cmid = 0 if message_id else conversation_message_id
        await self.call(
            "messages.pin",
            peer_id=peer_id,
            message_id=message_id or None,
            cmid=cmid or None,
        )

    async def unpin_message(self, peer_id: int) -> None:
        await self.call("messages.unpin", peer_id=peer_id, group_id=self.group_id)

    async def answer_event(self, event_id: str, user_id: int, peer_id: int, text: str) -> None:
        event_data = json.dumps({"type": "show_snackbar", "text": text}, ensure_ascii=False)
        await self.call(
            "messages.sendMessageEventAnswer",
            event_id=event_id,
            user_id=user_id,
            peer_id=peer_id,
            event_data=event_data,
        )

    async def user_name(self, user_id: int) -> str:
        response = await self.call("users.get", user_ids=user_id)
        if not response:
            return f"id{user_id}"
        user = response[0]
        return (
            " ".join(part for part in (user.get("first_name"), user.get("last_name")) if part)
            or f"id{user_id}"
        )


class BotsLongPoll:
    def __init__(self, api: VkApiClient, logger: logging.Logger | None = None):
        self.api = api
        self.logger = logger or logging.getLogger(__name__)

    async def events(self) -> AsyncIterator[dict]:
        server: LongPollServer | None = None
        failures = 0
        while True:
            try:
                if server is None:
                    server = await self.api.get_long_poll_server()
                response = await self.api.client.get(
                    server.server,
                    params={"act": "a_check", "key": server.key, "ts": server.ts, "wait": 25},
                    timeout=30.0,
                )
                response.raise_for_status()
                payload = response.json()
                failed = int(payload.get("failed", 0))
                if failed == 1:
                    server = LongPollServer(server.server, server.key, str(payload["ts"]))
                    continue
                if failed in {2, 3, 4}:
                    server = None
                    continue
                server = LongPollServer(server.server, server.key, str(payload["ts"]))
                failures = 0
                for update in payload.get("updates", []):
                    yield update
            except asyncio.CancelledError:
                raise
            except (httpx.HTTPError, ValueError, KeyError, VkApiError) as error:
                failures += 1
                delay = min(30, 2 ** min(failures, 5))
                self.logger.warning("Ошибка VK Long Poll: %s; повтор через %s сек.", error, delay)
                server = None
                await asyncio.sleep(delay)
