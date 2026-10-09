"""Test-chat commands and routing, kept separate from the production service."""
from __future__ import annotations

from .models import new_poll_state
from .service import PollService


class TestPollService(PollService):
    __test__ = False

    async def _notify_admins(self, text: str) -> None:
        # Test polls must not generate production administrators' notifications.
        return

    async def handle_message_event(self, event: dict) -> None:
        message = event.get("object", {}).get("message", {})
        text = str(message.get("text", "")).strip()
        peer_id = int(message.get("peer_id", 0))
        user_id = int(message.get("from_id", 0))
        if text.split()[:1] == ["/demo"] and peer_id == self.settings.peer_id:
            if not self.is_admin(user_id):
                return
            args = text.split()[1:]
            if len(args) != 1 or args[0] not in {str(n) for n in range(10, 16)} | {"20"}:
                await self._send(peer_id, "Тестовый состав: /demo 10–15 или /demo 20")
                return
            total = int(args[0])
            fields = [p for p in self.state["players"].values() if p["position"] == "field"]
            keepers = [p for p in self.state["players"].values()
                       if p["position"] == "goalkeeper"]
            keeper_count = 2 if total == 15 and len(keepers) == 2 else total // 5
            roster = fields[:total - keeper_count] + keepers[:keeper_count]
            if len(roster) != total:
                await self._send(peer_id, "Не хватает тестовых игроков в справочнике.")
                return
            if not self.poll or not self.poll.get("is_open"):
                await self.create_poll()
            async with self.lock:
                poll = new_poll_state(self.poll["poll_date"], self.poll["question"], peer_id)
                for key in ("poll_id", "message_id", "conversation_message_id", "random_id",
                            "teams_requested"):
                    if key in self.poll:
                        poll[key] = self.poll[key]
                for i, p in enumerate(roster, 1):
                    poll["manual_yes_voters"][f"manual:{i}"] = {
                        "label": p["name"], "added_by_user_id": user_id,
                        "added_by_name": "Тестовый состав", "added_at": self.now().isoformat(),
                    }
                poll["manual_yes_seq"] = total
                poll["last_total_yes_count"] = total
                poll["notified_yes"] = True
                self.state["current_poll"] = poll
                self.save()
                await self.refresh_teams("Изменён тестовый состав командой /demo.")
                await self._refresh_poll_message(poll)
            await self._send(peer_id, f"Тестовый состав: {len(roster)} игроков. Теперь /teams.")
            return
        await super().handle_message_event(event)


class TestChatRouter:
    __test__ = False

    def __init__(self, production, test):
        self.production = production
        self.test = test

    async def handle_update(self, event: dict) -> None:
        obj = event.get("object", {})
        message = obj.get("message", obj)
        peer_id = int(message.get("peer_id", 0))
        command = str(message.get("text", "")).split()[:1]
        private_test_command = (
            peer_id > 0 and peer_id == int(message.get("from_id", 0))
            and command and command[0] in {"/players", "/rating", "/position", "/alias", "/stats"}
        )
        target = self.test if (
            peer_id == self.test.settings.peer_id or private_test_command
        ) else self.production
        await target.handle_update(event)
