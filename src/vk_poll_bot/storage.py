from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path


class JsonStateRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.backup_path = self.path.with_name(f"{self.path.name}.bak")

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
                    json.load(current_file)
            except (OSError, ValueError, json.JSONDecodeError):
                pass
            else:
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
