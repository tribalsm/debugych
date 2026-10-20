# JavaScript / TypeScript и Playwright в gVisor

## Поддерживаемый проект

Загрузите ZIP или отдельные UTF-8 файлы: `index.html` в корне, локальные `.js/.mjs/.cjs/.ts/.tsx/.jsx` модули, `.css`, `.json` и документ требований. `demo/sample-ts-app` содержит воспроизводимый пример с намеренно неверным уменьшением счётчика.

Это фиксированный профиль для браузерного приложения. esbuild собирает локальные script entries из HTML, разрешает относительные импорты и транспилирует TypeScript/JSX; React и React DOM 19.1.0 встроены в образ. Полная проверка типов `tsc` не выполняется. Произвольные серверы Node, Vite-конфигурация, npm scripts/lifecycle hooks, зависимости и lockfile загруженного проекта не исполняются. Неизвестная зависимость — ошибка сборки, не дефект продукта. Для новых зависимостей нужен пересмотр доверенного образа, а не разрешение `npm install` внутри задания.

AI-анализ создаёт Playwright-план через настроенного OpenAI-compatible провайдера. План сохраняется в Test Studio, редактируется и экспортируется в `.js`; Playwright понимает также TypeScript-код тестов. Генератор получает контракт профиля: `import {test,expect} from '@playwright/test'`, `await page.goto('/')`, baseURL `http://127.0.0.1:4173`. Смешанный pytest/Playwright-план отклоняется; язык определяется сохранённым фреймворком, не произвольной командой клиента.

## Исполнение и безопасность

API передаёт только валидированный снимок файлов и тестов. Supervisor выбирает один из двух администраторских образов и создаёт контейнер с обязательным `runtime=runsc`. Клиент не выбирает image, entrypoint, args, mounts, env, runtime или Docker-параметры. Отсутствие gVisor/образа закрывает исполнение; небезопасного fallback нет.

В браузерном профиле: UID/GID 10000, readonly root, без Docker socket, host mounts, host IPC, capabilities, внешней сети и секретов; `no-new-privileges`. Лимиты: CPU 1, RAM/swap 1024 MiB, 256 PID, 512 FD, размер отдельного файла 8 MB, tmpfs `/tmp` 192 MiB `noexec,nosuid,nodev`. Образы, браузеры и инструменты устанавливаются только при доверенной сборке.

Сборка, статический HTTP-сервер на loopback, Node, тесты и Chromium находятся **в одном** одноразовом gVisor-контейнере. Порт не публикуется. Разрешены browser requests к внутреннему origin; дополнительно действует CSP. Chromium запускается с отключённым собственным sandbox внутри gVisor: граница изоляции недоверенного кода здесь — gVisor, а не флаг Chromium. Не используются `--ipc=host`, `SYS_ADMIN`, privileged или host network. `--disable-dev-shm-usage` направляет временные файлы в ограниченный tmpfs.

Тест: 7 с; assertion: 2.5 с; план: 35 с; процесс Playwright: 40 с; supervisor: 60 с; janitor удаляет просроченные контейнеры. Все процессы уничтожаются при удалении контейнера. Слоты общие с Python, максимум два задания. CPU/RAM/PID лимиты действуют на весь контейнер, включая дочерние процессы. Эти лимиты не заменяют будущие пользовательские квоты и авторизацию.

## Отчёты и скриншоты

Сохранённый запуск содержит SHA256 снимка, runtime, image ID, результаты кейсов с test UUID, traceback, время и логи. Автоматическая fixture снимает PNG viewport 960×640 после браузерного кейса, включая assertion-падение, и собирает console/page errors. Скриншот привязан к модулю теста; ошибка захвата не подменяется картинкой. Квоты: до 8 PNG, каждый до 400 kB, суммарный бюджет скриншотов 1.2 MB; отчёты до 400 kB каждый; не более 10 артефактов и 2.8 MB base64 на ответ. При превышении бюджета часть скриншотов отсутствует.

`playwright-report.json` — нормализованные реальные кейсы, browser observations и статистика. `coverage-istanbul.json` — совместимый Istanbul coverage map. Локальные модули проекта транспилируются в JavaScript и инструментируются до bundling; библиотечный код не входит в метрики. Счётчики объединяются между кейсами; имена coverage-файлов заканчиваются `.compiled.js`. В UI явно указано, что это покрытие **собранного JavaScript**, а не строки исходного TypeScript; source-map привязка пока не реализована. Если страница не загрузила инструментированные модули, покрытие отсутствует. Оценка LLM не используется.

Supervisor валидирует bounded data-only envelope, PNG signature/dimensions/chunks/CRC, JSON, UUID и принадлежность тесту. Worker сохраняет отдельные blob с серверными UUID, размером и SHA256. API выдаёт артефакт только по паре run UUID + artifact UUID, перепроверяет hash, выставляет `nosniff`, CSP sandbox и attachment. Загруженные HTML/JS и отчётный HTML не обслуживаются на origin приложения. UI показывает PNG и безопасно отображаемые данные, скачивает JSON. История запусков позволяет выбрать старые артефакты после редактирования проекта.

Отчёты и картинки — наблюдения из недоверенного проекта. Код внутри контейнера может вмешаться в них; hash гарантирует сохранность сохранённого blob, не истинность результата. Артефакты могут содержать данные, показанные самим проектом. Не считайте их независимым доказательством корректности.

## Bug Proof и границы Fix & Verify

Assertion-падение Playwright получает Reproduced; collection/build errors, timeout, неожиданный expected status и runtime page errors исключаются из Confirmed. После явной проверки требования пользователем исходный снимок повторяется в gVisor с закреплённым image ID и тем же набором кейсов. Только после совпадения возможен Confirmed.

AI Engine теперь поддерживает generation/verification/apply для существующих JS/TS/JSX/TSX implementation-модулей. Тесты и конфигурация не меняются; syntax/build и три прогона выполняются в gVisor, apply требует отдельного подтверждения. Транспорт, серверное согласие и ограничения: `ai-engine.md`.

## Воспроизведение

```sh
docker compose up --build -d --wait
# Для тестов без живого LLM: явно подключить подготовленный провайдер.
docker compose -f docker-compose.yml -f compose.test.yml up --build -d --wait
python tests/compose/playwright_smoke.py
docker compose exec -T supervisor python < tests/compose/playwright_probe.py
cd apps/web
PLAYWRIGHT_BASE_URL=http://127.0.0.1:8080 COMPOSE_CONTRACT_TEST=1 npm run test:e2e
```

Тестовый AI-провайдер явно маркируется в UI и записях. Он не моделирует исполнение: Chromium, сборка, тесты, coverage и скриншоты реальны. Обычный Compose не включает этого провайдера.

Документация инструментов: [Playwright Docker](https://playwright.dev/docs/docker), [Playwright reporters](https://playwright.dev/docs/test-reporters), [esbuild API](https://esbuild.github.io/api/). Встроенный runtime закрепляет Playwright 1.64.1, esbuild 0.28.2 и Istanbul instrumenter 6.0.3 через lockfile.
