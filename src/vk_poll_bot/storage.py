from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from .ratings import valid_rating


class JsonStateRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.backup_path = self.path.with_name(f"{self.path.name}.bak")
        self.history_backup_path = self.path.with_name(f"{self.path.name}.before-team-history.bak")

    def load(self) -> dict:
        if not self.path.exists():
            return {"schema_version": 1, "current_poll": None, "schedule": {}}
        try:
            with self.path.open("r", encoding="utf-8") as state_file:
                data = json.load(state_file)
        except (OSError, ValueError, json.JSONDecodeError):
            if not self.backup_path.exists():
                raise
            with self.backup_path.open("r", encoding="utf-8") as state_file:
                data = json.load(state_file)
        if not isinstance(data, dict):
            raise ValueError("Корень state.json должен быть объектом")
        return data

    def save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            try:
                with self.path.open("r", encoding="utf-8") as current_file:
                    current_data = json.load(current_file)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
                if ("team_history" in data and isinstance(current_data, dict)
                        and "team_history" not in current_data):
                    self._backup_before_history()
                shutil.copy2(self.path, self.backup_path)
                os.chmod(self.backup_path, 0o600)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                json.dump(data, temporary_file, ensure_ascii=False)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.chmod(temporary_path, 0o600)
            os.replace(temporary_path, self.path)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    def _backup_before_history(self) -> None:
        """Keep the pre-upgrade state once; ordinary rolling backups may be replaced later."""
        if self.history_backup_path.exists():
            return
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(dir=self.path.parent, delete=False) as backup:
                temporary_path = Path(backup.name)
                with self.path.open("rb") as source:
                    shutil.copyfileobj(source, backup)
                backup.flush()
                os.fsync(backup.fileno())
            os.chmod(temporary_path, 0o600)
            try:
                os.link(temporary_path, self.history_backup_path)
            except FileExistsError:
                pass
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


def import_player_registry(repository: JsonStateRepository, source: Path) -> int:
    """Import the prepared roster once, preserving the production poll and statistics."""
    if not source.exists():
        return 0
    state = repository.load()
    if state.get("players"):
        return 0
    players = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(players, dict) or not players:
        raise ValueError("Подготовленный справочник должен содержать игроков")
    for key, player in players.items():
        if not isinstance(player, dict) or not isinstance(player.get("name"), str):
            raise ValueError(f"Некорректный игрок: {key}")
        position = player.get("position")
        if position not in {"field", "goalkeeper"} or (
            position == "field" and not valid_rating(player.get("rating"))
        ) or (position == "goalkeeper" and player.get("rating") is not None):
            raise ValueError(f"Некорректные роль или рейтинг: {key}")
    state["players"] = players
    repository.save(state)
    source.rename(source.with_name(source.name + ".imported"))
    return len(players)
