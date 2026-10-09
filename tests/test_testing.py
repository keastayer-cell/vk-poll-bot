import asyncio
from types import SimpleNamespace

from fakes import FakeApi, make_settings

from vk_poll_bot.storage import JsonStateRepository
from vk_poll_bot.testing import TestChatRouter, TestPollService


def test_router_isolates_chat_and_private_test_commands():
    class Service:
        def __init__(self, peer):
            self.settings = SimpleNamespace(peer_id=peer)
            self.events = []

        async def handle_update(self, event):
            self.events.append(event)

    async def scenario():
        production, test = Service(2000000002), Service(2000000001)
        router = TestChatRouter(production, test)
        events = [
            {"object": {"message": {"peer_id": 2000000002, "text": "/teams"}}},
            {"object": {"message": {"peer_id": 2000000001, "text": "/demo 10"}}},
            {"object": {"peer_id": 2000000001, "user_id": 10}},
            {"object": {"message": {"peer_id": 10, "from_id": 10, "text": "/rating 20 7"}}},
            {"object": {"message": {"peer_id": 10, "from_id": 10, "text": "/announce"}}},
        ]
        for event in events:
            await router.handle_update(event)
        assert production.events == [events[0], events[4]]
        assert test.events == [events[1], events[2], events[3]]

    asyncio.run(scenario())


def test_demo_seeds_only_test_poll_and_sends_no_admin_notifications(tmp_path):
    async def scenario():
        api = FakeApi()
        bot = TestPollService(api, make_settings(tmp_path),
                              JsonStateRepository(tmp_path / "state.json"))
        bot.state["players"] = {
            f"guest:{i}": {"name": f"Игрок {i}", "position": "field" if i < 16
                           else "goalkeeper", "rating": 5 if i < 16 else None}
            for i in range(20)
        }
        for total in (10, 11, 12, 13, 14, 15, 20):
            await bot.handle_message_event({"object": {"message": {
                "peer_id": bot.settings.peer_id, "from_id": 10, "text": f"/demo {total}",
            }}})
            assert len(bot.poll["manual_yes_voters"]) == total
            await bot.handle_message_event({"object": {"message": {
                "peer_id": bot.settings.peer_id, "from_id": 10, "text": "/teams",
            }}})
            if total < 20:
                assert "Вратари (распределите сами)" in bot.state["team_distribution"]["text"]
                assert api.sent[-1][1].startswith(("⚽ КОМАНДА", "Команды уже распределены"))
            else:
                assert "Записалось 20" in api.sent[-1][1]
        assert all(peer == bot.settings.peer_id for peer, _, _ in api.sent)

    asyncio.run(scenario())
