# Дебагыч / DEBUGYCH

**AI QA Assistant — «Находит. Доказывает. Исправляет. Проверяет».**

React + TypeScript + Vite + Tailwind; FastAPI + SQLAlchemy + Alembic; PostgreSQL, Redis, Celery; одноразовые Python / pytest и JS/TS / Playwright Test Runner с обязательным gVisor. Русский интерфейс: Dashboard, Projects, Test Studio, Bug Lab, Reports.

**Технический MVP:** [готовность и соответствие кейсу №9](docs/mvp-readiness.md). Автономный Live QA подтверждён на независимых Python и JS/TS контролях: по 2/2 дефекта, Python-кандидат 17/17 тестов + 4/4 приватных oracle, JS/TS-кандидат 4/4 + 4/4 oracle. Ручных корректировок результатов нет; патчи не применены. Новый Python-прогон: 5 запросов, включая один timeout, $0.62995 консервативного резерва; фактический счёт неизвестен. Предыдущие две неудачные Python-попытки сохранены в [истории валидации](docs/autonomous-ai-validation.md). Это подтверждение на небольших контролях, не гарантия для любых проектов.

Финальные проверки: **178 backend**, **10 browser E2E**, **4 автономных API E2E**, 7 gVisor syntax/discovery, Python/Playwright security probes, негативные Fix & Verify и Compose smoke. Техническое ядро заморожено для перехода к UI/UX и согласованному 3D-маскоту.

Для нового загруженного проекта кнопка «Автономный QA» запрашивает согласие на весь QA-цикл. Неоднозначность приводит к `manual_review_required`, а не автоматическому принятию. Применение проверенного патча по-прежнему требует отдельного подтверждения. Существующий отдельный AI-анализ и ручной Bug Lab сохранены.

## Рабочие возможности

- Создание проектов; загрузка Python, JS/TS/JSX/TSX, HTML/CSS/JSON, Java, требований `.md`, `.pdf`, `.docx`; ZIP с защитой от traversal и symlink. До 10 МБ на загрузку, ZIP до 100 элементов / 30 МБ после распаковки.
- AI Engine: извлечение требований с проверяемыми цитатами, обзор структуры, генерация Gherkin и pytest / Playwright через единый OpenAI-compatible адаптер. Strict JSON Schema/Pydantic, privacy filter, серверное согласие, retries/timeouts и сохраняемые токеновые/денежные резервы. Настройка: `docs/ai-engine.md`.
- Редактирование сценариев и экспорт `.feature`, `.py`, `.js`.
- **Загруженные Python-проекты и AI-сгенерированные pytest выполняются** в отдельных одноразовых контейнерах `runsc`. Сохраняются реальные results, traceback, coverage.py, UUID тестов, SHA256 снимка и ID образа.
- **Загруженные JS/TS-проекты и Playwright выполняются** в отдельном gVisor-профиле: Chromium, esbuild, локальный сайт, screenshot после браузерного кейса, JSON-отчёт, console/page errors и измеренное Istanbul-покрытие собранного JavaScript. История артефактов в Test Studio / Reports, скачивание PNG/JSON. Контракт и ограничения: `docs/javascript-playwright.md`.
- Assertion failure AI-теста получает **Reproduced**, а не Confirmed: ожидание требует независимой проверки. Import error, сбой harness, timeout и OOM не объявляются дефектами продукта.
- Доверенное демо магазина: подготовленный план, настоящее падение, Bug Proof, diff, проверка патча в копии, применение отдельным подтверждением.
- Для загруженных Python и JS/TS-проектов: review ожидания по требованию, повтор Bug Proof в gVisor, AI-предложение с серверным diff, контроль исходника / целевого теста / полной регрессии, история и применение только отдельным подтверждением. Описание: `docs/fix-and-verify.md`.
- Без API-ключа приложение запускается; AI-анализ недоступен явно, демо и запуск ранее сохранённых pytest / Playwright работают.

## Docker Compose

Нужен Linux Docker Engine с зарегистрированным **gVisor/runsc**. Обычный runtime не используется как fallback для загрузок. Однократная подготовка Debian/Ubuntu Docker-хоста:

```sh
# Docker и Compose уже должны быть установлены.
# Скрипт устанавливает runsc и ПЕРЕЗАПУСКАЕТ Docker.
sudo bash infra/install-gvisor.sh
```

Затем из корня репозитория:

```sh
cp .env.example .env
docker compose up --build
# Совместимое имя; wrapper устанавливается скриптом выше:
docker-compose up --build
```

Приложение: **http://localhost:8080**. OpenAPI: **http://localhost:8080/docs**. БД, Redis, runner и supervisor не публикуют порты. API применяет Alembic; worker ждёт healthchecks. Токен worker → supervisor генерируется в отдельный private named volume, не хранится в репозитории.

В текущем Windows-окружении реально проверены Ubuntu 26.04 / WSL2, Docker 29.1.3, Compose 2.40.3 и gVisor `release-20261012.0`. Из PowerShell в корне:

```powershell
.\scripts\compose.ps1 up --build
# Либо явно:
wsl -d Ubuntu -u root -- docker compose up --build
```

Helper предпочитает Windows Docker CLI; иначе использует Ubuntu WSL. Linux engine должен иметь runsc; Windows-контейнеры не поддерживаются. Foreground `up` удерживает WSL активным. Для фонового `up -d` нужна активная WSL-сессия: после закрытия последних сессий WSL может остановить systemd services.

Compose, PostgreSQL, Celery и границы sandbox проверены реальными прогонами. **Предыдущий JS/TS live-отчёт: [docs/js-live-workflow.md](docs/js-live-workflow.md)**. gpt-6-luna сгенерировала неизменённые тесты, выявившие 2/2 JS-дефекта; Bug Proof, AI-diff и gVisor verify прошли, патч не применён. Набор принят после явной проверки агентом: LLM-reviewer ошибочно его отклонял, поэтому полностью автономный quality gate пока не подтверждён. Новая серия ограничена 12 live POST и $2 консервативного резерва (факт $1.99111). История предыдущего Python/JS live-этапа: `docs/live-ai-validation.md`; контрактные результаты: `docs/benchmark.md`. Контрактный provider явно маркируется; результаты gVisor реальные.

## Выполнение своего Python-проекта

1. Создайте обычный проект, загрузите `.py` / ZIP с исходниками и документ требований.
2. Настройте LLM в `.env`, перезапустите API / worker. Нажмите «AI-анализ» и подтвердите передачу текста выбранному провайдеру.
3. Проверьте и при необходимости отредактируйте Gherkin / pytest в Test Studio.
4. Нажмите «Запустить тесты». API фиксирует неизменяемый снимок исходников и тестов. Последующие правки не меняют уже отправленный код и не получают старый результат автоматически.
5. Изучите фактический результат, traceback, coverage, runtime и SHA256. Reproduced / Suspected не означают независимое подтверждение дефекта.

Для исправления откройте Bug Lab: подтвердите корректность assertion по требованию с обоснованием, дождитесь повторного воспроизведения, получите diff, проверьте патч и весь сохранённый pytest-план в gVisor. Только затем отдельно подтвердите применение. До этого исходники не меняются; изменение проекта или тестов после verify блокирует apply. Доступен ZIP исправленного проекта и история версий. Для предложения нужен LLM-ключ; проверка уже сохранённого предложения и применение ключа не требуют.

Профиль исполнения: Python / pytest, до 100 `.py` файлов, 300 000 символов на файл, 40 тестовых модулей, 16 000 символов на тест, общий снимок до 2 МБ UTF-8. Пути внутри ZIP сохраняются; импорты должны соответствовать структуре проекта.

Зависимости фиксированы в sandbox-образе: Python 3.12, pytest, coverage, FastAPI/Pydantic, httpx. `pip install` из пользовательского проекта не запускается, интернет отключён. Недостающая зависимость — ошибка окружения. Дополнительные пакеты добавляются только через отдельно проверенный образ. Java остаётся загрузкой и анализом без исполнения.

## Выполнение JS/TS-проекта

Загрузите `index.html` в корне, локальные JS/TS модули, CSS и требования; пример — `demo/sample-ts-app`. После AI-анализа проверьте Playwright-план в Test Studio и запустите его. В контейнере esbuild собирает script entries из HTML, Chromium открывает локальный сайт на loopback. Произвольные npm scripts, конфигурация проекта, установка зависимостей и пользовательский backend не запускаются. React 19 предустановлен; неизвестные зависимости дают ошибку сборки.

Результаты и скриншоты появляются в Test Studio; в Reports доступны история, скачивание нормализованного Playwright JSON и Istanbul coverage map. Покрытие относится к собранному JavaScript, не к исходным строкам TypeScript. Ошибка ожидания требует human review и повторного Bug Proof; JS/TS Fix & Verify доступен для существующих implementation-модулей. Полное описание: `docs/javascript-playwright.md`, `docs/ai-engine.md`.

## Изоляция

Только доверенный supervisor имеет Docker socket. API, worker, web и контейнеры тестов его не получают. Worker передаёт валидированный JSON: исходники и тесты. Через API supervisor невозможно передать Docker image, command, mounts, runtime, environment или privileged.

Каждому заданию: `runtime=runsc`, UID/GID 10000, `network=none`, read-only rootfs, без host mounts, capabilities и секретов. Python-профиль: tmpfs `/tmp` 96 МБ, RAM 384 МБ без swap, 1 CPU, 128 host tasks, RLIMIT_NPROC 16 guest processes, 128 файловых дескрипторов, файл до 1 МБ, тесты до 30 с / внешний deadline 45 с. Playwright-профиль: tmpfs 192 МБ, RAM 1024 МБ без swap, 1 CPU, 256 PID, 512 FD, файл до 8 МБ, suite deadline 35 с / supervisor 60 с; Chromium не получает host IPC или SYS_ADMIN. Два запуска одновременно между обоими профилями. Контейнер удаляется в `finally`; janitor удаляет просроченные задания после сбоя контроллера. Подробнее: `docs/javascript-playwright.md`.

gVisor защищает границу хоста; тестовый процесс и его отчёты остаются недоверенными. Враждебный проект может пытаться искажать собственные отчёты. Поэтому результат не превращается автоматически в Confirmed и не доказывает полную корректность. Supervisor валидирует результаты и связывает их со снимком. Модель угроз: `docs/runner-security.md`.

Конфигурация предназначена для локальной команды. Для публичного многопользовательского сервиса нужны авторизация, квоты и выделенный Docker-хост runner. Supervisor с Docker authority — доверенная управляющая инфраструктура.

## AI

```env
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=ваша-модель
LLM_API_KEY=ваш-ключ
```

Перезапуск: `docker compose up -d --force-recreate api worker`. Endpoint `/chat/completions`, strict JSON schema (явный `json_object` mode для совместимых старых провайдеров); 40 000 символов контекста, 4000 output tokens, до двух попыток на этап и общий бюджет задания. Перед отправкой требуется согласие с hash проекта/провайдера. Известные секреты фильтруются; `.env`/oracle/private-key файлы исключаются. Фильтр эвристический: проверьте данные до согласия. Подробные лимиты, тарифы и известные ограничения: `docs/ai-engine.md`.

Без ключа live LLM не проверен. Воспроизводимая проверка использует **явно тестовый провайдер**, отключённый в обычном Compose:

```sh
docker compose -f docker-compose.yml -f compose.test.yml up --build -d
python tests/compose/stack_smoke.py
python tests/compose/fix_verify_smoke.py
docker compose exec -T supervisor python < tests/compose/sandbox_probe.py
```

Подменяется только внешний LLM transport; upload, БД, Redis, Celery, gVisor, coverage, Bug Lab и экспорт настоящие. Security probe проверяет auth, identity, secrets, mounts/socket, сеть, rootfs, процессы, OOM, timeout и очистку. Возврат к обычной конфигурации:

```sh
docker compose up --build -d --remove-orphans
```

## Разработка без Compose

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Отдельные терминалы из корня:
.\.venv\Scripts\python.exe -m uvicorn services.runner.main:app --host 127.0.0.1 --port 8090
.\.venv\Scripts\python.exe -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
cd apps/web
npm ci
npm run dev
```

Это SQLite/background-tasks режим только доверенного демо; загрузки на хосте не исполняются. Python читает переменные процесса; `.env` автоматически читает Compose. Для frontend против Compose задайте `$env:API_TARGET='http://127.0.0.1:8080'` перед `npm run dev`.

## Тесты и демонстрация

```powershell
.\.venv\Scripts\python.exe -m pytest
cd apps/web
npm run build
npx playwright install chromium
npm run test:e2e
# Для работающего Compose с compose.test.yml:
$env:PLAYWRIGHT_BASE_URL='http://127.0.0.1:8080'
$env:COMPOSE_CONTRACT_TEST='1'
npm run test:e2e
```

При обычном E2E нужны локальные серверы выше. HTML report, screenshots и traces: `apps/web/playwright-report`, `apps/web/test-results`. CI содержит отдельный Compose/gVisor job; удалённый GitHub CI здесь не запускался.

Демо для жюри: Dashboard → демопроект → демоплан → Test Studio → 13 passed / 1 failed → Bug Lab → diff `>` → `>=` → проверка в копии → 14 passed → отдельное применение → Reports / экспорт. План и патч подготовлены явно; прогоны настоящие. Полная корректность приложения не доказана.

## Следующие этапы

Живая проверка с пользовательским ключом; независимый автоматический oracle для произвольных требований (сейчас human review + replay); source-map coverage, trace/video, дополнительные dependency profiles; отмена задач, авторизация/пользовательские квоты; нагрузочные PDF 50+ страниц; pgvector при необходимости. Новые контрольные проекты и приватные evaluator oracle находятся в `evaluation/`; их результаты и пропущенные проверки описаны в `docs/validation-ai-engine.md`.

## Качество тестирования и независимый benchmark

Test Planner v2 требует сценарий для каждого извлечённого требования. Его checklist проверяет применимость границ, неверных входов, исключений, состояний, инвариантов, сочетаний параметров, негативных сценариев и документированной авторизации. Непредусмотренное требованиями поведение не добавляется. Метки сценариев не доказывают полноту assertions.

Завершённые прогоны загруженных проектов содержат `quality` в `GET /api/runs/{id}`: измеренные строки/ветви, требования с исполнившимися assertions, непроверенные требования, исполняемость модулей и ошибки инфраструктуры. Метаданные фиксируются вместе со снимком. Количество тестов не превращается в оценку качества; отсутствующее измерение — `null`.

Независимый evaluator исполняет неизменные сгенерированные тесты на эталоне, версиях с отдельными дефектами и контрольных мутациях. Oracle, расположения ошибок и преобразования эталона находятся вне AI-контекста. Только gVisor исполняет этот код. См. `docs/benchmark.md` для фактических результатов и ограничений.

```sh
# Контрактная проверка инфраструктуры; не оценка настоящей LLM:
docker compose -f docker-compose.yml -f compose.test.yml up --build -d --wait
python tests/compose/benchmark.py --output work/benchmark-contract.json

# Обычный Compose использует LLM_BASE_URL / LLM_API_KEY / LLM_MODEL из .env.
# При отсутствии ключа приложение продолжает работать, benchmark пишет NOT_VERIFIED.
docker compose up -d --remove-orphans --wait
python tests/compose/benchmark.py --allow-external --output work/benchmark-live.json
```

`--allow-external` означает согласие отправить только исходники и требования из `evaluation/projects/` настроенному провайдеру. Сначала просмотрите эти файлы. Скрипт не загружает oracle/variants и не включает контрактный provider автоматически. Live-генерация и запуск оцениваются без автоматического подтверждения Bug Proof и применения патча; дальнейший review и Fix & Verify выполняются в UI. API-ключ не передавайте через аргументы CLI и не добавляйте в репозиторий.

После ручного review / Bug Proof / проверки патча в UI можно дополнить тот же live-отчёт без новой генерации и без изменения исходников:

```sh
python tests/compose/benchmark.py --resume-report work/benchmark-live.json --output work/benchmark-live-reviewed.json
```

Resume выполняет только чтение API и изолированные контрольные прогоны; ничего не отправляет LLM и не подтверждает/применяет патчи. Проект и тесты должны соответствовать исходному снимку, поэтому применённый или отредактированный проект потребует отдельной новой оценки.
