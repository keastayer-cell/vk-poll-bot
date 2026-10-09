import asyncio
from urllib.parse import parse_qs

import httpx
import pytest

from vk_poll_bot.api import VkApiClient, VkApiError


@pytest.mark.parametrize("message_id,cmid,response", [
    (42, 0, {"42": 1}),
    (0, 12, [{"conversation_message_id": 12, "response": 1}]),
])
def test_delete_only_bot_message_for_everyone(message_id, cmid, response):
    async def handler(request):
        params = parse_qs(request.content.decode())
        assert request.url.path.endswith("/messages.delete")
        assert params["delete_for_all"] == ["1"]
        assert params["peer_id"] == ["2000000001"]
        assert params["group_id"] == ["123"]
        if message_id:
            assert params["message_ids"] == [str(message_id)]
            assert "cmids" not in params
        else:
            assert params["cmids"] == [str(cmid)]
            assert "message_ids" not in params
        return httpx.Response(200, json={"response": response})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = VkApiClient("token", 123, client=client)
            await api.delete_message(2000000001, message_id=message_id,
                                     conversation_message_id=cmid)
    asyncio.run(scenario())


@pytest.mark.parametrize("response", [{"42": 0}, [], [{"response": 0, "error": {}}]])
def test_delete_requires_vk_confirmation(response):
    async def handler(request):
        return httpx.Response(200, json={"response": response})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = VkApiClient("token", 123, client=client)
            with pytest.raises(VkApiError):
                await api.delete_message(2000000001, message_id=42)
    asyncio.run(scenario())


def test_conversation_members_paginates_and_skips_groups():
    async def handler(request):
        params = parse_qs(request.content.decode())
        assert request.url.path.endswith("/messages.getConversationMembers")
        assert params["group_id"] == ["123"]
        offset = int(params["offset"][0])
        pages = {
            0: {"count": 3, "items": [{"member_id": 20}, {"member_id": -123}],
                "profiles": [{"id": 20, "first_name": "Иван", "last_name": "Иванов"}]},
            2: {"count": 3, "items": [{"member_id": 21}],
                "profiles": [{"id": 21, "first_name": "Пётр", "last_name": "Петров"}]},
        }
        return httpx.Response(200, json={"response": pages[offset]})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            api = VkApiClient("token", 123, client=client)
            assert await api.conversation_members(2_000_000_001) == {
                "20": "Иван Иванов", "21": "Пётр Петров",
            }

    asyncio.run(scenario())


def test_api_client_unwraps_response() -> None:
    async def handler(request):
        assert request.url.path.endswith("/groups.getLongPollServer")
        return httpx.Response(
            200,
            json={"response": {"server": "https://lp.example", "key": "key", "ts": "1"}},
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            api = VkApiClient("token", 123, client=http_client)
            server = await api.get_long_poll_server()
            assert server.server == "https://lp.example"
            assert server.ts == "1"

    asyncio.run(scenario())


def test_api_client_raises_vk_error() -> None:
    async def handler(request):
        return httpx.Response(200, json={"error": {"error_code": 5, "error_msg": "denied"}})

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            api = VkApiClient("bad", 123, client=http_client)
            try:
                await api.get_long_poll_server()
            except VkApiError as error:
                assert error.code == 5
            else:
                raise AssertionError("VkApiError expected")

    asyncio.run(scenario())


def test_send_message_keeps_conversation_message_id() -> None:
    async def handler(request):
        body = request.content.decode()
        assert "peer_ids=2000000001" in body
        return httpx.Response(
            200,
            json={
                "response": [
                    {
                        "peer_id": 2_000_000_001,
                        "message_id": 0,
                        "conversation_message_id": 42,
                    }
                ]
            },
        )

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http_client:
            api = VkApiClient("token", 123, client=http_client)
            sent = await api.send_message(2_000_000_001, "test")
            assert sent.message_id == 0
            assert sent.conversation_message_id == 42
            assert sent.random_id > 0

    asyncio.run(scenario())
