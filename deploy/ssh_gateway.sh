#!/usr/bin/env bash
set -euo pipefail

case "${SSH_ORIGINAL_COMMAND:-}" in
    probe)
        echo 'VK deploy gateway is available; no deployment performed.'
        ;;
    preflight)
        if [[ -e /etc/systemd/system/vk-poll-bot.service.d/test-runtime.conf ]]; then
            echo 'Test runtime is active; production deployment is blocked.' >&2
            exit 1
        fi
        command -v rsync >/dev/null
        ;;
    upload)
        exec /usr/bin/python3 /usr/local/lib/vk-bot-receive-release.py
        ;;
    apply)
        exec sudo -n /usr/local/sbin/vk-bot-apply-release
        ;;
    *)
        echo 'Only probe, preflight, upload and apply commands are allowed.' >&2
        exit 1
        ;;
esac
