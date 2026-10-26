# Проверка платформ, 27.10.2026

Дополнение: в ветке `release/macos-web-support` добавлены macOS-launcher, диагностический режим и отдельный ZIP. См. [macos.md](macos.md). Это реализация поддержки запуска с Linux backend, а не подтверждение испытаний на настоящем Mac.

Проверена текущая ветка `release/web-product-release`. Платные AI-запросы, переустановка gVisor и перезапуск общих контейнеров не выполнялись.

| Платформа | Проверка | Итог |
|---|---|---|
| Windows x64 | Node 24.18.0, production server: HTML, JS, favicon, manifest, отклонение .env и traversal. Предыдущий полный браузерный release-набор и Desktop Pet переход | PASS в доступной Windows-среде |
| Linux x64 | Linux 6.18.33.2 внутри WSL2; Node 22.23.3, тот же production server: 6 проверок | PASS |
| Linux production image | Текущий `infra/web.Dockerfile`: npm ci, TypeScript, Vite, Nginx; тест nginx -t и HTTP HTML/favicon в read-only контейнере без внешней сети | PASS |
| Linux backend | API health из Ubuntu, существующий Linux Docker, обязательный runsc; отдельный свежий non-root gVisor smoke | PASS; полный новый AI-цикл не запускался |
| Отдельный Linux-хост | Нет отдельной физической машины; выполнены Linux-сборка и контейнерные проверки в WSL2 | Не отдельная установка с нуля |
| macOS Intel / Apple Silicon | Настоящего macOS-хоста / Safari в доступной среде нет | НЕ ПРОВЕРЕНО |
| Linux ARM64 | Сборка и запуск на ARM64 не выполнялись | НЕ ПРОВЕРЕНО |

## Что это означает для macOS

Веб-интерфейс не является Windows-приложением: Tauri не входит в web release. Его можно открывать браузером, но macOS/Safari здесь не проверялись. Отдельного macOS-приложения или .dmg в архиве нет.

Полный backend зависит от Linux gVisor. По официальной документации gVisor требует Linux 5.6+ и поддерживает x86_64 / ARM64: https://gvisor.dev/docs/user_guide/install/ . Нативный backend с gVisor непосредственно в macOS не предусмотрен. Нужна Linux VM или Linux backend. Наличие Docker Desktop само по себе не подтверждает регистрацию runsc в его Linux engine и работоспособность всего стека.

Существующий установщик `infra/install-gvisor.sh` рассчитан на Debian/Ubuntu с apt и systemd. Это не macOS-инсталлятор. `scripts/start-local.ps1` рассчитан на Windows. Для Linux при готовом backend доступен `node scripts/serve-web.mjs`, либо обычный существующий Docker Compose. Для Mac такой Node frontend с совместимым Linux backend является возможной схемой, но не подтверждённой здесь установкой.

Не следует маркировать текущий архив как полностью протестированный Windows/Linux/macOS release. Подтверждён Windows + WSL2 и Linux x64 на уровне сборки, сервера и контейнерного исполнения; macOS и ARM64 требуют реальных проверок.

## Доказательства

Логи в `outputs/web-integration/`: `platform-windows.log`, `platform-linux.log`, `platform-nginx.log`, `platform-gvisor.log`, `linux-build.log`. Проверка Node-сервера воспроизводится командой `node scripts/check-platform.mjs`; она запускает временный сервер на loopback 18798 и завершает только собственный процесс.

Linux Docker image собран под отдельным тегом `debugych-web-release-platform-check:local`. Проверочные контейнеры автоматически удалены. Рабочий backend не перезапускался. Дополнительных постоянных серверов нет.
