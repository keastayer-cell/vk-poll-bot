from pathlib import Path
from types import SimpleNamespace

from vk_poll_bot.api import SentMessage


class FakeApi:
    def __init__(self):
        self.sent = []
        self.edited = []
        self.pinned = []
        self.unpinned = []
        self.answers = []
        self.names = {}
        self.next_message_id = 100

    async def send_message(self, peer_id, text, keyboard=None):
        self.sent.append((peer_id, text, keyboard))
        self.next_message_id += 1
        return SentMessage(message_id=self.next_message_id, random_id=self.next_message_id + 1000)

    async def edit_message(
        self,
        peer_id,
        text,
        keyboard=None,
        *,
        message_id=0,
        conversation_message_id=0,
    ):
        self.edited.append((peer_id, message_id, conversation_message_id, text, keyboard))

    async def pin_message(self, peer_id, *, message_id=0, conversation_message_id=0):
        self.pinned.append((peer_id, message_id, conversation_message_id))

    async def unpin_message(self, peer_id):
        self.unpinned.append(peer_id)

    async def answer_event(self, event_id, user_id, peer_id, text):
        self.answers.append((event_id, user_id, peer_id, text))

    async def user_name(self, user_id):
        return self.names.get(user_id, f"User {user_id}")


def make_settings(tmp_path: Path, **overrides):
    values = {
        "peer_id": 2_000_000_001,
        "admin_ids": (10,),
        "timezone": "Europe/Moscow",
        "yes_threshold": 3,
        "poll_question": "Идете?",
        "initial_schedule": {
            "poll_days": "mon,thu",
            "poll_hour": 8,
            "poll_minute": 0,
            "deadline_days": "mon,thu",
            "deadline_hour": 15,
            "deadline_minute": 0,
            "close_days": "mon,thu",
            "close_hour": 20,
            "close_minute": 0,
            "remind_mon_days": "mon",
            "remind_mon_hour": 19,
            "remind_mon_minute": 45,
            "remind_thu_days": "thu",
            "remind_thu_hour": 18,
            "remind_thu_minute": 15,
        },
        "data_dir": tmp_path,
    }
    values.update(overrides)
    return SimpleNamespace(**values)
