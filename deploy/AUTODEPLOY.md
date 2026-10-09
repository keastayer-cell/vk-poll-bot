# Автодеплой VK-бота

GitHub Actions выполняет проверки и выкладку при push в `main`.
Сейчас `AUTO_DEPLOY_ENABLED=false`: deploy-job пропускается даже при ручном запуске.
CI при этом проверяет код без доступа к серверу.

Repository secrets: `VPS_HOST`, `VPS_USER=vkdeploy`, `DEPLOY_KEY`, `SSH_KNOWN_HOSTS`.
На сервере настроен отдельный SSH-пользователь с forced command:

- `probe` — проверить доступ, ничего не изменяя;
- `preflight` — проверить, что тестовый runtime выключен;
- `upload` — принять только файлы приложения в `/opt/vk-poll-bot-release`;
- `apply` — запустить фиксированный `/usr/local/sbin/vk-bot-apply-release`.

Произвольные команды, интерактивный shell и SSH forwarding этим ключом запрещены.
Sudo разрешён только для фиксированного root-owned deploy-скрипта без аргументов.
Исходники конфигурации находятся в `ssh_gateway.sh`, `receive_release.py`
и `apply_release.sh`; изменение этих файлов требует отдельной установки
администратором в `/usr/local/bin/vk-bot-deploy-gateway`,
`/usr/local/lib/vk-bot-receive-release.py` и `/usr/local/sbin/vk-bot-apply-release`.

Перед активацией нужно отдельно согласовать перенос рейтингов и отключить
`/etc/systemd/system/vk-poll-bot.service.d/test-runtime.conf`. Пока этот файл
существует, workflow блокируется до загрузки файлов, а apply-скрипт — до
изменения зависимостей, исходников или сервиса.

После разрешённой выкладки обновляются только `src`, `main.py`, `requirements.txt`
в `/opt/vk-poll-bot`. `.env`, состояние и тестовый пакет остаются на сервере.
После перезапуска проверяется стабильность процесса 20 секунд и доступность
VK API/Long Poll через `main.py --check`. Heartbeat и автоматического отката нет.

Для будущего включения установить repository variable `AUTO_DEPLOY_ENABLED=true`.
Это разрешает следующую выкладку; саму переменную сейчас менять не нужно.
