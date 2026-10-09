#!/usr/bin/env bash
set -euo pipefail

release_root=/opt/vk-poll-bot-release
bot_root=/opt/vk-poll-bot
service=vk-poll-bot

# Refuse before changing code or dependencies; activation is a separate operation.
if [[ -e /etc/systemd/system/vk-poll-bot.service.d/test-runtime.conf ]]; then
    echo 'Test runtime is active; production deployment is blocked.' >&2
    exit 1
fi
test -f "$release_root/main.py"
test -f "$release_root/requirements.txt"
test -d "$release_root/src/vk_poll_bot"
test -f "$bot_root/.env"
test -x "$bot_root/.venv/bin/python"
command -v rsync >/dev/null
"$bot_root/.venv/bin/python" - "$release_root" <<'PY'
import sys
from pathlib import Path
root = Path(sys.argv[1])
for path in [root / "main.py", *(root / "src").rglob("*.py")]:
    compile(path.read_bytes(), str(path), "exec")
PY

if [[ "${1:-}" == --check ]]; then
    echo 'Release preflight passed; no files changed and service not restarted.'
    exit 0
fi
if [[ $# != 0 ]]; then
    echo 'Usage: apply_release.sh [--check]' >&2
    exit 2
fi

runuser -u vkbot -- "$bot_root/.venv/bin/pip" install -q -r "$release_root/requirements.txt"
runuser -u vkbot -- "$bot_root/.venv/bin/python" -m pip check
rsync -a --delete --chown=vkbot:vkbot "$release_root/src/" "$bot_root/src/"
install -o vkbot -g vkbot -m 644 "$release_root/main.py" "$bot_root/main.py"
install -o vkbot -g vkbot -m 644 "$release_root/requirements.txt" "$bot_root/requirements.txt"

systemctl restart "$service"
initial_pid=$(systemctl show "$service" --property=MainPID --value)
initial_restarts=$(systemctl show "$service" --property=NRestarts --value)
for attempt in $(seq 1 20); do
    if ! systemctl is-active --quiet "$service" \
        || [[ "$initial_pid" == 0 ]] \
        || [[ "$(systemctl show "$service" --property=MainPID --value)" != "$initial_pid" ]] \
        || [[ "$(systemctl show "$service" --property=NRestarts --value)" != "$initial_restarts" ]]; then
        journalctl -u "$service" -n 60 --no-pager
        exit 1
    fi
    sleep 1
done

# --check only reads VK API/Long Poll configuration; it does not process events.
if ! runuser -u vkbot -- "$bot_root/.venv/bin/python" "$bot_root/main.py" --check; then
    journalctl -u "$service" -n 60 --no-pager
    exit 1
fi
echo 'VK bot deployed: process remained stable and VK API check passed.'
