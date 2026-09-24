import asyncio

import httpx

from vk_poll_bot.api import VkApiClient, VkApiError


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
