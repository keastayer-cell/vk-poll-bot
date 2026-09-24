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
