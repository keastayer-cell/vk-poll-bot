from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from .api import VkApiError
from .keyboards import decode_payload, poll_keyboard
from .models import new_poll_state, normalize_state
from .votes import (
    add_manual_vote,
    counts,
    evaluate_threshold,
    format_status,
    parse_plus_one,
    remove_manual_vote,
    set_vote,
)

TIME_KEYS = {
    "poll": ("poll_hour", "poll_minute", "запуск опроса"),
    "deadline": ("deadline_hour", "deadline_minute", "дедлайн"),
    "close": ("close_hour", "close_minute", "закрытие"),
    "remind_mon": ("remind_mon_hour", "remind_mon_minute", "напоминание в понедельник"),
    "remind_thu": ("remind_thu_hour", "remind_thu_minute", "напоминание в четверг"),
}
DAY_KEYS = {
    "poll": "poll_days",
    "deadline": "deadline_days",
    "close": "close_days",
    "remind_mon": "remind_mon_days",
    "remind_thu": "remind_thu_days",
}
VALID_DAYS = {"mon", "tue", "wed", "thu", "fri", "sat", "sun"}
RU_WEEKDAYS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)
RU_MONTHS = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)


class PollService:
    def __init__(self, api, settings, repository, logger: logging.Logger | None = None):
        self.api = api
        self.settings = settings
        self.repository = repository
        self.logger = logger or logging.getLogger(__name__)
        self.state = normalize_state(repository.load(), settings.initial_schedule)
        self.lock = asyncio.Lock()
        self.pending_announcements: set[int] = set()
        self.reschedule_callback = None

    @property
    def poll(self) -> dict | None:
        return self.state.get("current_poll")

    @property
    def schedule(self) -> dict:
        return self.state["schedule"]

    def save(self) -> None:
        self.repository.save(self.state)

    def now(self) -> datetime:
        return datetime.now(ZoneInfo(self.settings.timezone))

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.settings.admin_ids

    def render_poll(self, poll: dict | None = None) -> str:
        poll = poll or self.poll
        if poll is None:
            return "Активного опроса нет."
        try:
            poll_date = datetime.strptime(poll["poll_date"], "%Y-%m-%d")
            date_text = (
                f"{RU_WEEKDAYS[poll_date.weekday()]}, {poll_date.day} {RU_MONTHS[poll_date.month]}"
            )
        except (KeyError, TypeError, ValueError):
            date_text = str(poll.get("poll_date", ""))
        result = counts(poll)
        yes_names = [
            voter["name"]
            for voter in poll.get("voters", {}).values()
            if voter.get("choice") == "yes"
        ]
        no_names = [
            voter["name"]
            for voter in poll.get("voters", {}).values()
            if voter.get("choice") == "no"
        ]
        guest_names = [vote["label"] for vote in poll.get("manual_yes_voters", {}).values()]
        roster = [
            f"✅ Идут ({result.yes}): {', '.join(yes_names) or '—'}",
            f"➕ Гости ({result.manual_yes}): {', '.join(guest_names) or '—'}",
            f"❌ Не идут ({result.no}): {', '.join(no_names) or '—'}",
        ]
        if result.total_yes >= self.settings.yes_threshold:
            progress = f"🔥 Команда собрана: {result.total_yes} / {self.settings.yes_threshold}"
        else:
            missing = self.settings.yes_threshold - result.total_yes
            progress = (
                f"👥 Собрано: {result.total_yes} / {self.settings.yes_threshold}"
                f"  ·  Не хватает: {missing}"
            )
        if poll.get("is_open"):
            heading = f"⚽ {poll['question']}"
            footer = "Гость: +1 ФИО  ·  Получить статистику: /status"
        else:
            heading = "🏁 Голосование завершено"
            footer = "Итоговый состав сохранён."
        return "\n".join([heading, f"📅 {date_text}", "", *roster, "", progress, "", footer])

    async def _send(self, peer_id: int, text: str):
        return await self.api.send_message(peer_id, text)

    async def _notify_admins(self, text: str) -> None:
        for admin_id in self.settings.admin_ids:
            try:
                await self._send(admin_id, text)
            except Exception as error:
                self.logger.warning("Не удалось уведомить admin_id=%s: %s", admin_id, error)

    async def _send_threshold_events(self, poll: dict) -> None:
        for event in evaluate_threshold(poll, self.settings.yes_threshold):
            if event.audience == "chat":
                await self._send(self.settings.peer_id, event.text)
            else:
                await self._notify_admins(event.text)

    async def _refresh_poll_message(self, poll: dict | None = None) -> None:
        poll = poll or self.poll
        if not poll or not (poll.get("message_id") or poll.get("conversation_message_id")):
            return
        keyboard = poll_keyboard(poll["poll_date"], disabled=not poll.get("is_open", False))
        message_id = int(poll.get("message_id", 0))
        conversation_message_id = 0 if message_id else int(poll.get("conversation_message_id", 0))
        await self.api.edit_message(
            int(poll["peer_id"]),
            self.render_poll(poll),
            keyboard,
            message_id=message_id,
            conversation_message_id=conversation_message_id,
        )

    async def create_poll(self, poll_date: str | None = None, force: bool = False) -> bool:
        if self.settings.peer_id <= 0:
            raise RuntimeError("VK_PEER_ID не настроен; отправьте /where в тестовом чате")
        target_date = poll_date or self.now().strftime("%Y-%m-%d")
        async with self.lock:
            current = self.poll
            if (
                current
                and current.get("is_open")
                and current.get("poll_date") == target_date
                and not force
            ):
                return False
            if current and current.get("is_open"):
                current["is_open"] = False
                try:
                    await self._refresh_poll_message(current)
                except Exception as error:
                    self.logger.warning("Не удалось закрыть предыдущий опрос: %s", error)
            poll = new_poll_state(target_date, self.settings.poll_question, self.settings.peer_id)
            sent_message = await self.api.send_message(
                self.settings.peer_id,
                self.render_poll(poll),
                poll_keyboard(target_date),
            )
            poll["message_id"] = sent_message.message_id
            poll["conversation_message_id"] = sent_message.conversation_message_id
            poll["random_id"] = sent_message.random_id
            self.state["current_poll"] = poll
            self.save()
            if sent_message.message_id or sent_message.conversation_message_id:
                try:
                    pin_message_id = sent_message.message_id
                    await self.api.pin_message(
                        self.settings.peer_id,
                        message_id=pin_message_id,
                        conversation_message_id=(
                            0 if pin_message_id else sent_message.conversation_message_id
                        ),
                    )
                except Exception as error:
                    self.logger.warning("Опрос создан, но не закреплён: %s", error)
            else:
                self.logger.info("VK пока не вернул ID опроса; ожидаю событие message_reply")
            try:
                await self._send(
                    self.settings.peer_id,
                    "Я создал опрос — проголосуйте.\n\n"
                    "Если хотите пригласить человека на игру, напишите в чат:\n"
                    "+1 ФИО\n\n"
                    "Например: +1 Иванов Иван\n\n"
                    "Обязательно укажите имя приглашённого, чтобы всем было понятно, "
                    "кого добавили.",
                )
            except Exception as error:
                self.logger.warning("Не удалось отправить инструкцию к опросу: %s", error)
            date_text = datetime.strptime(target_date, "%Y-%m-%d").strftime("%d.%m.%Y")
            await self._notify_admins(
                f'📋 Я запустил опрос "{date_text}".\n\nЯ буду сообщать Вам о его результатах.'
            )
            return True

    async def handle_vote_event(self, event: dict) -> None:
        obj = event.get("object", {})
        user_id = int(obj.get("user_id", 0))
        peer_id = int(obj.get("peer_id", 0))
        event_id = str(obj.get("event_id", ""))
        payload = decode_payload(obj.get("payload"))
        if payload.get("command") != "vote":
            return
        answer = "Не удалось принять голос"
        async with self.lock:
            poll = self.poll
            if peer_id != self.settings.peer_id or poll is None:
                answer = "Это не активный опрос"
            elif not poll.get("is_open"):
                answer = "Голосование уже закрыто"
            elif payload.get("poll_date") != poll.get("poll_date"):
                answer = "Этот опрос уже неактуален"
            elif payload.get("choice") not in {"yes", "no"}:
                answer = "Неизвестный вариант ответа"
            else:
                choice = payload["choice"]
                if not poll.get("conversation_message_id"):
                    poll["conversation_message_id"] = int(obj.get("conversation_message_id", 0))
                name = await self.api.user_name(user_id)
                previous = set_vote(poll, user_id, name, choice)
                await self._send_threshold_events(poll)
                self.save()
                await self._refresh_poll_message(poll)
                labels = {"yes": "ДА", "no": "Нет"}
                answer = f"Ваш голос: {labels[choice]}"
                if previous == choice:
                    answer = f"Голос уже учтён: {labels[choice]}"
        if event_id and user_id and peer_id:
            try:
                await self.api.answer_event(event_id, user_id, peer_id, answer)
            except Exception as error:
                self.logger.warning("Не удалось показать ответ на кнопку: %s", error)

    async def handle_outgoing_message(self, event: dict) -> None:
        obj = event.get("object", {})
        message = obj.get("message", obj)
        poll = self.poll
        if not poll:
            return
        random_matches = int(message.get("random_id", 0)) == int(poll.get("random_id", 0))
        text_matches = str(message.get("text", "")) == self.render_poll(poll)
        if not (random_matches or text_matches):
            return
        poll["message_id"] = int(message.get("id", 0))
        poll["conversation_message_id"] = int(message.get("conversation_message_id", 0))
        self.save()
        try:
            message_id = int(poll.get("message_id", 0))
            await self.api.pin_message(
                self.settings.peer_id,
                message_id=message_id,
                conversation_message_id=(
                    0 if message_id else int(poll.get("conversation_message_id", 0))
                ),
            )
        except Exception as error:
            self.logger.warning("Не удалось закрепить опрос после подтверждения VK: %s", error)
        else:
            self.logger.info(
                "Опрос закреплён после message_reply: message_id=%s, cmid=%s",
                poll.get("message_id"),
                poll.get("conversation_message_id"),
            )

    async def add_guest(self, label: str, user_id: int, user_name: str) -> None:
        async with self.lock:
            poll = self.poll
            if not poll or not poll.get("is_open"):
                await self._send(self.settings.peer_id, "Сейчас нет открытого опроса.")
                return
            add_manual_vote(poll, label, user_id, user_name, self.now())
            await self._send_threshold_events(poll)
            self.save()
            await self._refresh_poll_message(poll)
            await self._send(
                self.settings.peer_id,
                f"Добавлен: {label}\n{format_status(poll, self.settings.yes_threshold)}",
            )

    async def remove_guest(self, query: str) -> None:
        async with self.lock:
            poll = self.poll
            if not poll or not poll.get("is_open"):
                await self._send(self.settings.peer_id, "Сейчас нет открытого опроса.")
                return
            removed = remove_manual_vote(poll, query)
            if removed is None:
                await self._send(self.settings.peer_id, "Подходящий виртуальный голос не найден.")
                return
            await self._send_threshold_events(poll)
            self.save()
            await self._refresh_poll_message(poll)
            await self._send(
                self.settings.peer_id,
                f"Убран: {removed['label']}\n{format_status(poll, self.settings.yes_threshold)}",
            )

    async def close_poll(self) -> None:
        async with self.lock:
            poll = self.poll
            if not poll or not poll.get("is_open"):
                return
            poll["is_open"] = False
            self.save()
            try:
                await self._refresh_poll_message(poll)
            except Exception as error:
                self.logger.warning("Не удалось обновить закрытый опрос: %s", error)
            try:
                await self.api.unpin_message(self.settings.peer_id)
            except Exception as error:
                self.logger.warning("Не удалось открепить закрытый опрос: %s", error)
            try:
                await self._send(
                    self.settings.peer_id,
                    f"Голосование закрыто.\n{format_status(poll, self.settings.yes_threshold)}",
                )
            except Exception as error:
                self.logger.warning("Не удалось отправить итог закрытого опроса: %s", error)
            self.state["current_poll"] = None
            self.save()

    async def check_deadline(self) -> None:
        poll = self.poll
        today = self.now().strftime("%Y-%m-%d")
        if (
            not poll
            or poll.get("poll_date") != today
            or not poll.get("is_open")
            or poll.get("notified_deadline")
        ):
            return
        poll["notified_deadline"] = True
        self.save()
        total = counts(poll).total_yes
        if total < self.settings.yes_threshold:
            deadline_time = (
                f"{self.schedule['deadline_hour']:02d}:{self.schedule['deadline_minute']:02d}"
            )
            await self._notify_admins(
                f"⚠️ {deadline_time} — в опросе только {total} «ДА» "
                f"из {self.settings.yes_threshold} нужных."
            )

    async def remind_game(self, reminder_key: str) -> None:
        poll = self.poll
        today = self.now().strftime("%Y-%m-%d")
        if (
            not poll
            or poll.get("poll_date") != today
            or reminder_key in poll.get("sent_reminders", [])
            or counts(poll).total_yes < self.settings.yes_threshold
        ):
            return
        await self._send(
            self.settings.peer_id,
            "Мужчины, напоминаю что сегодня вы играете. Всем приятной игры и без травм 🏃",
        )
        poll.setdefault("sent_reminders", []).append(reminder_key)
        self.save()

    def schedule_text(self) -> str:
        s = self.schedule
        return (
            f"Опрос: {s['poll_days']} {s['poll_hour']:02d}:{s['poll_minute']:02d}\n"
            f"Дедлайн: {s['deadline_days']} {s['deadline_hour']:02d}:{s['deadline_minute']:02d}\n"
            f"Закрытие: {s['close_days']} {s['close_hour']:02d}:{s['close_minute']:02d}\n"
            f"Напоминание пн: {s['remind_mon_days']} "
            f"{s['remind_mon_hour']:02d}:{s['remind_mon_minute']:02d}\n"
            f"Напоминание чт: {s['remind_thu_days']} "
            f"{s['remind_thu_hour']:02d}:{s['remind_thu_minute']:02d}"
        )

    async def _reschedule(self) -> None:
        if self.reschedule_callback is None:
            return
        result = self.reschedule_callback()
        if inspect.isawaitable(result):
            await result

    async def set_time(self, args: list[str]) -> str:
        if not args:
            return self.schedule_text()
        if len(args) != 2 or args[0] not in TIME_KEYS:
            return "Формат: /settime poll|deadline|close|remind_mon|remind_thu ЧЧ:ММ"
        try:
            hour_text, minute_text = args[1].split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except ValueError:
            return "Время должно быть в формате ЧЧ:ММ"
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            return "Недопустимое время"
        hour_key, minute_key, label = TIME_KEYS[args[0]]
        self.schedule[hour_key], self.schedule[minute_key] = hour, minute
        self.save()
        await self._reschedule()
        return f"Изменено: {label} — {hour:02d}:{minute:02d}"

    async def set_days(self, args: list[str]) -> str:
        if not args:
            return self.schedule_text()
        if len(args) != 2 or args[0] not in DAY_KEYS:
            return "Формат: /setdays poll|deadline|close|remind_mon|remind_thu mon,thu"
        days = [day.strip().lower() for day in args[1].split(",")]
        if not days or any(day not in VALID_DAYS for day in days):
            return "Допустимые дни: mon,tue,wed,thu,fri,sat,sun"
        self.schedule[DAY_KEYS[args[0]]] = ",".join(days)
        self.save()
        await self._reschedule()
        return f"Дни изменены: {args[0]} — {','.join(days)}"

    async def handle_message_event(self, event: dict) -> None:
        message = event.get("object", {}).get("message", {})
        peer_id = int(message.get("peer_id", 0))
        user_id = int(message.get("from_id", 0))
        text = str(message.get("text", "")).strip()
        if user_id <= 0 or not text:
            return
        command_text = text.split("@", 1)[0] if text.startswith("/") else text
        parts = command_text.split()
        command = parts[0].lower() if parts else ""
        args = parts[1:]
        if command == "/where":
            await self._send(peer_id, f"peer_id={peer_id}\nuser_id={user_id}")
            return
        if user_id in self.pending_announcements and command != "/cancel":
            self.pending_announcements.remove(user_id)
            await self._send(self.settings.peer_id, text)
            await self._send(peer_id, "Объявление опубликовано.")
            return
        if command == "/cancel" and self.is_admin(user_id):
            self.pending_announcements.discard(user_id)
            await self._send(peer_id, "Ввод объявления отменён.")
            return
        if peer_id != self.settings.peer_id:
            if command in {"/start", "/help"} and self.is_admin(user_id):
                await self._send(
                    peer_id,
                    "Личные уведомления администратора включены. "
                    "Сюда будут приходить сообщения о запуске опроса и дедлайне.",
                )
                return
            if command == "/announce" and self.is_admin(user_id):
                self.pending_announcements.add(user_id)
                await self._send(peer_id, "Пришлите следующим сообщением текст объявления.")
            return
        if command in {"/start", "/help"}:
            await self._send(
                peer_id,
                "Команды: /poll, /status, /close, /plus1, /minus1, /settime, /setdays, /where",
            )
            return
        if command == "/status":
            await self._send(peer_id, self.render_poll())
            return
        if command == "/poll" and self.is_admin(user_id):
            created = await self.create_poll(force=False)
            if not created:
                await self._refresh_poll_message()
            return
        if command == "/close" and self.is_admin(user_id):
            await self.close_poll()
            return
        if command == "/announce" and self.is_admin(user_id):
            self.pending_announcements.add(user_id)
            await self._send(peer_id, "Пришлите следующим сообщением текст объявления.")
            return
        if command == "/settime" and self.is_admin(user_id):
            await self._send(peer_id, await self.set_time(args))
            return
        if command == "/setdays" and self.is_admin(user_id):
            await self._send(peer_id, await self.set_days(args))
            return
        user_name = await self.api.user_name(user_id)
        if command == "/plus1" and self.is_admin(user_id):
            await self.add_guest(" ".join(args) or f"Гость от {user_name}", user_id, user_name)
            return
        if (command == "/minus1" or text == "-1") and self.is_admin(user_id):
            await self.remove_guest(" ".join(args))
            return
        guest_name = parse_plus_one(text, user_name)
        if guest_name is not None:
            await self.add_guest(guest_name, user_id, user_name)

    async def handle_update(self, event: dict) -> None:
        event_type = event.get("type")
        try:
            if event_type == "message_event":
                await self.handle_vote_event(event)
            elif event_type == "message_new":
                await self.handle_message_event(event)
            elif event_type == "message_reply":
                await self.handle_outgoing_message(event)
        except VkApiError as error:
            self.logger.error("Ошибка VK API при обработке события: %s", error)
        except Exception:
            self.logger.exception("Ошибка при обработке VK event=%r", event)
