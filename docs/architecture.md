# Архитектура и контракты

## Границы

Web → FastAPI → PostgreSQL; API ставит UUID задания в Redis / Celery. Worker извлекает документы, вызывает LLM или HTTP runner. API не импортирует и не исполняет исходники пользователя. В локальном режиме вместо PostgreSQL/Redis доступны SQLite / FastAPI BackgroundTasks; это режим разработки, не модель производственной отказоустойчивости.

- `apps/api`: REST, хранение файлов по UUID, SQLAlchemy, очередь.
- `services/ai`: RequirementAnalyzer (контекст), CodeAnalyzer (AST), TestPlanner (связи), TestGenerator (LLM JSON), FailureAnalyzer (классификация), FixGenerator (подготовленный демопатч), VerificationEngine (сравнение наборов тестов).
- `services/runner/main.py`: legacy HTTP service доверенного демо; вход только `{ "fixed": false|true }`. Он не принимает загруженный код. Выход: status, duration, passed, failed, cases, logs, coverage, fixed, trusted_demo.
- `services/runner/supervisor.py`: доверенный controller загруженных Python-проектов, отдельный HTTP `/execute` с Bearer token, только структурированный `SandboxJob`. Создаёт одноразовый обязательный runsc container по зафиксированному image ID, без mounts и сети. Контракт и результат в `contracts.py`, код внутри sandbox в `harness.py` и `pytest_bootstrap.py`. Сетевые/collection/resource ошибки не становятся Confirmed.
- `demo/sample-python-app`: неизменяемые доверенные исходники и контрольный pytest. Требования отдельно от oracle, описания дефекта не отправляются в AI-контекст.

В Docker worker находится в backend и execution networks; API имеет execution для чтения health. Legacy runner и supervisor находятся только во внутренней execution. Только supervisor имеет Docker socket; worker/API/web его не имеют. Sandbox получает только JSON через stdin, не имеет управляющей сети, DB/Redis/LLM/control credentials или host mounts. При отсутствии runsc выполнение загрузок закрыто. Политика изоляции и граница доверия отчётов: `runner-security.md`.

## Данные

Project: UUID, name, demo, created_at. Record: UUID, project_id FK, kind, data JSON, created_at. История выдаётся по timestamp; миграция 002 добавляет поле для существующих записей.

| kind | Логическая сущность | Контракт data |
|---|---|---|
| file | ProjectFile | name, size, storage (UUID, не возвращается клиенту) |
| requirement | Requirement | key, text |
| test | TestCase | title, requirement, requirement_id, gherkin, code, framework, origin, result |
| run | Job / TestExecution / VerificationRun | operation, status, error; immutable snapshot + SHA256 для загрузок, runtime/image ID; результат runner; bug_id, fix_id, assessment для demo verify |
| bug | BugFinding | requirement_id, run_id, expected, actual, file, line, traceback, code, steps, status |
| fix | FixProposal | bug_id, before, after, diff, verified, verification_id, assessment, applied, original_storage |

CoverageReport хранится в run.data.coverage в исходном coverage.py JSON. Логи и кейсы доступны через artifacts endpoint. Файловые screenshot/trace артефакты браузерной проверки пока остаются в Playwright report, не в API-хранилище.

JSON records выбраны ради небольшого первого среза; это не отдельные ORM модели для каждой конкурсной сущности. Внешние ссылки между документами проверяет прикладной код. Для дальнейшего развития вынести TestCase, Execution, Finding и Fix в отдельные таблицы с FK, revision и timestamps; добавить блокировки и идемпотентность постановки заданий.

## REST

| Метод / путь | Назначение |
|---|---|
| GET/POST /api/projects | Список / создание |
| GET /api/projects/{uuid} | Проект |
| GET/POST /api/projects/{uuid}/files | Метаданные / multipart file |
| POST /api/demo | Новый доверенный демопроект |
| POST /api/projects/{uuid}/analyze | 202 + id/status задания |
| GET /api/projects/{uuid}/requirements | Требования |
| GET /api/projects/{uuid}/test-cases | Сценарии |
| PATCH /api/test-cases/{uuid} | title, gherkin, code; только обычный проект |
| GET/POST /api/projects/{uuid}/runs | История / выполнение демо |
| GET /api/runs/{uuid} | Статус и результат |
| GET /api/runs/{uuid}/coverage | Измеренный coverage JSON |
| GET /api/runs/{uuid}/artifacts | logs, cases |
| GET /api/bugs?project_id={uuid} | Проблемы |
| GET /api/bugs/{uuid} | Доказательство |
| POST /api/bugs/{uuid}/propose-fix | Демо proposal / diff |
| POST /api/bugs/{uuid}/verify-fix | 202 + verification job |
| POST /api/bugs/{uuid}/apply-fix | `{ "confirm": true }`, только verified |
| GET /api/projects/{uuid}/fixes | История патчей |
| GET /api/exports?project_id={uuid}&format=feature|py|js | Скачивание |

Документация OpenAPI генерируется на `/docs`. Ошибки: 403 execution disabled, 404 missing, 409 invalid transition, 413 oversized, 422 validation, 503 AI / queue unavailable. UUID и input length проверяются Pydantic. UI показывает detail API. Запросы локальны, CORS не открыт; dev proxy Vite и production nginx предоставляют same origin.

## Состояния

Analyze: queued → analyzing → generating → completed / failed.
Run/verify: queued → running → completed / failed.
Cancellation: зарезервирована, endpoint отмены пока отсутствует.

Suspected означает предположение, reproduced — фактическое отклонение. Только контролируемое assertion-падение известного теста с проверяемым требованием получает confirmed. Произвольный failed-test автоматически не подтверждается. Успешная проверка исходного теста и всей прежней регрессии переводит в fix_verified. Применение — отдельная операция; меняет сохранённый файл после проверки before, сохраняет предыдущую версию. Оригинальная fixture в репозитории не изменяется.

## AI и ограничения

OpenAI-compatible `/chat/completions`, JSON object и Pydantic schema. От 1 до 2 попыток, лимит входа/выхода, HTTP timeout 90s; worker hard timeout 270s. JSON traceability проходит отдельную проверку. Загруженные инструкции рассматриваются как данные в системном prompt. Сгенерированный код никогда не исполняется в API / worker. Live LLM и провайдерская совместимость без ключа не проверены. pgvector отложен: нет embeddings pipeline и необходимости для небольшого контекста. Текущая версия не предоставляет отдельного поискового endpoint.

## Приоритет интеграции

1. Linux CI: Compose smoke, PostgreSQL migration и Celery end-to-end, quotas.
2. Внешний sandbox supervisor: одноразовая среда, ограниченный declarative artifact contract, без socket в API и sandbox.
3. Передача exact test/source hashes runner, независимый requirement oracle, фиксация версии плана.
4. Общая LLM-генерация fix с проверяемым unified diff, запретом изменения тестов и повторной верификацией хэшей.
5. Browser runner и артефакты в общем API, Istanbul coverage, затем quality/mutations.

Пункты 1–3 в части локального Compose, внешнего runsc supervisor и snapshots реализованы. Загруженные Python-проекты поддерживают Confirmed через human requirement review + replay и Fix Verified через три изолированных прогона. Модули `apps/api/bug_workflow.py`, `apps/api/sandbox_client.py`, `services/ai/patches.py`, UI `BugLab.tsx`; контракты и состояния описаны в `fix-and-verify.md`. State SHA256 охватывает исходники, документы, требования, Gherkin и тестовый код; row lock и copy-on-write защищают apply. Удалённый CI и полностью независимый автоматический oracle остаются будущей работой.

## JS/TS browser profile

`SandboxJob.profile=playwright` выбирает отдельный фиксированный image ID через supervisor. Он содержит Node, esbuild, Chromium/Playwright, React и Istanbul. `services/runner/playwright/` создаёт локальный сайт из root index.html и browser modules; сборка, тесты, HTTP и Chromium живут внутри одного runsc-контейнера без внешней сети. Пользовательские npm scripts не запускаются. Профиль pytest и его лимиты сохранены.

Runner возвращает bounded PNG/JSON envelope. `apps/api/run_artifacts.py` сохраняет blob с UUID/SHA256, а JSON run — метаданные. Endpoint `/api/runs/{rid}/artifacts/{aid}` проверяет принадлежность run и целостность; никакой загруженный HTML не обслуживается origin приложения. `RunArtifacts.tsx` показывает PNG, историю и скачивание JSON в Test Studio и Reports. Coverage — реальные Istanbul counters локальных модулей после трансляции в JS, без vendor metrics и без исходных TypeScript line mappings. Playwright assertion доступен для human review + replay Bug Proof; общий Fix & Verify теперь поддерживает Python и JS/TS implementation-модули. Подробности: `javascript-playwright.md`.

## AI Engine

Текущий этап заменил два отдельных HTTP-цикла единым `services/ai/adapter.py`: strict response schema, bounded stream, классификация retry/refusal/truncation, токеновые/денежные admission limits и metadata audit. `privacy.py` исключает credentials/oracle и редактирует известные секреты; `apps/api/ai_runtime.py` связывает каждый вызов с согласием по raw state hash и provider fingerprint. Таблица `ai_budgets` (Alembic 003) атомарно резервирует общие UTC-дневные квоты для нескольких workers; `Record(kind=ai_call)` хранит безопасные результаты попыток.

Два этапа генерации: document-grounded requirements с точными цитатами, затем связанный тестовый план. AST/text code structure не исполняет приложение. Важные изменения состояния до/во время генерации блокируют сохранение устаревшего плана. Требования сохраняют source/quote и участвуют в state hash.

JS/TS implementation-патчи теперь используют общий Fix & Verify: host не исполняет их синтаксическую проверку, вместо этого build/collection и исходный/целевой/регрессионный прогоны проверяются в gVisor. Тесты/конфигурация/ожидания остаются неизменными; отдельное apply-подтверждение сохранено. Протокол, финансовые допущения и честная граница live-проверки: `ai-engine.md`.
