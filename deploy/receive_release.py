"""Accept only regular application files into the unprivileged release directory."""
from __future__ import annotations

import shutil
import sys
import tarfile
from pathlib import Path, PurePosixPath


def receive(stream, target: Path) -> None:
    if target.is_symlink():
        raise ValueError("Release directory must not be a symlink")
    target.mkdir(mode=0o755, exist_ok=True)
    for child in target.iterdir():
        if child.is_dir() and not child.is_symlink():
            shutil.rmtree(child)
        else:
            child.unlink()
    total_size = 0
    with tarfile.open(fileobj=stream, mode="r|gz") as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("Invalid release path")
            if member.isdir():
                continue
            allowed = str(path) in {"main.py", "requirements.txt"} or (
                len(path.parts) == 3 and path.parts[:2] == ("src", "vk_poll_bot")
                and path.suffix == ".py" and not path.name.startswith(".")
            )
            if not allowed or not member.isfile():
                raise ValueError(f"Not an allowed application file: {member.name}")
            total_size += member.size
            if total_size > 10_000_000:
                raise ValueError("Release exceeds 10 MB")
            destination = target.joinpath(*path.parts)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            content = archive.extractfile(member)
            if content is None:
                raise ValueError("Missing file contents")
            with content, destination.open("wb") as output:
                shutil.copyfileobj(content, output)
            destination.chmod(0o644)
    for required in ("main.py", "requirements.txt", "src/vk_poll_bot/__init__.py"):
        if not (target / required).is_file():
            raise ValueError(f"Missing required file: {required}")


if __name__ == "__main__":
    receive(sys.stdin.buffer, Path("/opt/vk-poll-bot-release"))
