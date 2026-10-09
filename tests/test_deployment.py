import io
import runpy
import subprocess
import tarfile
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"
receive = runpy.run_path(str(DEPLOY / "receive_release.py"))["receive"]


def archive(extra=None):
    data = io.BytesIO()
    with tarfile.open(fileobj=data, mode="w:gz") as output:
        for name in ("main.py", "requirements.txt", "src/vk_poll_bot/__init__.py"):
            member = tarfile.TarInfo(name)
            member.size = 1
            output.addfile(member, io.BytesIO(b"\n"))
        if extra is not None:
            output.addfile(extra, io.BytesIO(b""))
    data.seek(0)
    return data


def test_receive_replaces_only_staging_contents(tmp_path):
    target = tmp_path / "release"
    target.mkdir()
    (target / "old.py").write_text("old")
    outside = tmp_path / "state.json"
    outside.write_text("keep")
    receive(archive(), target)
    assert not (target / "old.py").exists()
    assert (target / "main.py").read_text() == "\n"
    assert outside.read_text() == "keep"


@pytest.mark.parametrize("name", ["../state.json", "/tmp/escape.py", ".env", "state.json",
                                 "src/vk_poll_bot/../escape.py", "deploy/apply_release.sh"])
def test_receive_rejects_files_outside_application(tmp_path, name):
    with pytest.raises(ValueError):
        receive(archive(tarfile.TarInfo(name)), tmp_path / "release")


def test_receive_rejects_symlinks(tmp_path):
    member = tarfile.TarInfo("main.py")
    member.type = tarfile.SYMTYPE
    member.linkname = "/etc/passwd"
    with pytest.raises(ValueError):
        receive(archive(member), tmp_path / "release")


def test_gateway_rejects_arbitrary_ssh_commands():
    result = subprocess.run(["bash", str(DEPLOY / "ssh_gateway.sh")],
                            env={"SSH_ORIGINAL_COMMAND": "uname -a"},
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "Only probe" in result.stderr
