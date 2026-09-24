# Эксплуатация

## Проверка конфигурации и API

```bash
/opt/vk-poll-bot/.venv/bin/python /opt/vk-poll-bot/main.py --check
```

Успешный результат: `OK: VK API и Bots Long Poll доступны`.

## Запуск через systemd

```bash
sudo cp deploy/vk-poll-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vk-poll-bot
sudo systemctl status vk-poll-bot
```

Логи:

```bash
sudo journalctl -u vk-poll-bot -f
tail -f /opt/vk-poll-bot/bot.log
```

## Безопасная проверка

1. Оставить `ENABLE_SCHEDULER=0`.
2. Запустить бота в тестовой беседе.
3. Проверить `/where`, `/poll`, кнопки, `+1`, `/status` и `/close`.
4. Только после проверки указать рабочий `VK_PEER_ID`.
5. Включить `ENABLE_SCHEDULER=1` и перезапустить сервис.

Файл `.env` и `state.json` должны иметь права `600` и не должны попадать в Git.
