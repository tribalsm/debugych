# Проверка Compose и загруженных Python-проектов

19 октября 2026. Этот отчёт заменяет ограничения первого этапа из `validation.md` в части Docker и исполнения загрузок.

## Окружение

Ubuntu 26.04 LTS в WSL2, Linux 6.18.33.2. Установлены Docker Engine 29.1.3, Compose 2.40.3 и gVisor `release-20261012.0`. Engine работает внутри Ubuntu; Windows Docker Desktop не устанавливался. Compose доступен через `docker compose` и compatibility wrapper `docker-compose`.

## Выполнено

| Проверка | Фактический результат |
|---|---|
| `docker compose up --build -d` | Образы собраны, API/web/worker/runner/supervisor/PostgreSQL/Redis подняты; healthchecks прошли |
| PostgreSQL / Alembic | Миграции 001/002 применены, проекты/файлы/тесты/запуски сохраняются в PostgreSQL |
| Redis / Celery | Реальные задания анализа и исполнения прошли очередь и worker |
| Provider contract → uploaded execution | Загрузка calc.py + Markdown → план через локальный тестовый LLM transport → сохранённый pytest → runsc → реальное assertion-падение → coverage → Reproduced → экспорт |
| Browser E2E на Compose web:8080 | 6 сценариев приняты: 5 обычных успешных сценариев и одно ожидаемое assertion-падение дефектного магазина |
| Финальный обычный Compose без тестового провайдера | 6 browser tests приняты, 1 provider-only тест явно skipped; добавлена проверка восстановления устаревшего выбранного UUID |
| Backend suite | 47 passed: прежние проверки плюс 20 sandbox contract cases и 2 snapshot/fail-closed integration cases |
| Production frontend | TypeScript / Vite build прошёл |
| Sandbox boundaries | Auth, unknown Docker options, UID, capabilities, no-new-privileges, rootfs, secrets/socket, network, процессы, память, время, cleanup проверены реальным runsc |

Полный provider contract smoke: `tests/compose/stack_smoke.py`. Пример фактического запуска: uploaded `add(a,b): return a-b`, тест `assert add(2,3)==5`; 0 passed / 1 failed, покрытие единственной строки 100%, находка Reproduced. 100% покрытие этого простого примера не означает его корректность — дефект как раз обнаружен.

Внешний LLM был заменён **только в явно подключённом compose.test.yml** тестовым HTTP-провайдером. UI сообщает, что план подготовлен; origin `llm-contract-test`. Выполнение, PostgreSQL, Redis/Celery и coverage не подменялись. Live LLM без API-ключа по-прежнему не проверен. Обычный Compose не содержит тестовый провайдер.

После возврата обычной конфигурации отдельно проверен запуск сохранённого теста загрузки без API-ключа: health ai_available=false, sandbox_available=true, runtime runsc, фактический 0 passed / 1 failed. Результат и fingerprint сохранены в outputs/uploaded-run-result.json. Подготовленное происхождение теста сохраняется в origin и отображается в Test Studio даже после выключения тестового провайдера.

## Что подтвердили security probes

Контейнеры создаются с реальным runtime runsc и image ID. UID/GID 10000, CapEff=0, NoNewPrivs=1. Запись в rootfs и setuid(0) отклонены. Docker socket, project-data, DB/Redis/LLM/control credentials отсутствуют. Внешнее TCP-подключение невозможно.

Проверка процесса: RLIMIT_NPROC 16 блокирует дальнейшие fork; проверка возвращает passed. RAM: запрос 600 МБ завершает sandbox с OOMKilled=true / exit 137. Время: sleep(100) прерывается harness примерно через 30 с. Обе ошибки сохраняются как инфраструктурные, не баги продукта. После каждой проверки контейнеров с ownership label не остаётся. Docker inspect подтверждает memory/swap, 1 CPU, host PID limit и отсутствие bind mounts.

Изначальная проверка fork через большой pytest-процесс упиралась в RAM раньше NPROC; это был реальный сработавший лимит, не PASS проверки PID. Проверка уточнена: дочерние fork выполняет минимальный Python-процесс, и отдельно подтверждён именно NPROC.

## Исправления при интеграции

- Alembic CLI в контейнере не находил `apps`: добавлен `prepend_sys_path=.`.
- Учтён жизненный цикл WSL: systemd Docker не удерживает дистрибутив сам; для фоновой сессии оставлен активный WSL-процесс, README рекомендует foreground `up`.
- Добавлены fail-closed healthcheck и отказ 503 до постановки задания при недоступном supervisor.
- Источник и тесты фиксируются снимком; новые правки не получают старые результаты.
- Launcher pytest/coverage переведён в Python isolated mode, импортирует инструменты до project path.
- Выход sandbox валидируется отдельно; счётчики пересчитываются, Confirmed для AI-тестов не назначается.
- Vite перестал следить за playwright-report/test-results/dist, чтобы генерация отчётов не сбрасывала открытый экран через HMR.
- При переходе от SQLite к PostgreSQL UI восстанавливает устаревший выбранный UUID. Browser fixtures и Swagger переведены на same-origin адреса, устраняя зависимость от отдельного Windows/WSL relay порта 8000.
- Тестовое окружение pytest вынесено в conftest: отдельная DB/storage, без внешнего LLM key даже при запуске одного тестового файла.

## Артефакты и ограничения

`apps/web/playwright-report` содержит HTML, screenshots и trace ожидаемого дефекта; `work/sandbox-probes.log` — фактический вывод boundary/resource тестов. В outputs копируется отчёт и обновлённый архив исходников.

Generic Fix & Verify для загрузок, выполнение загруженного Playwright/Java, авторизация/квоты, нагрузочные 50+ страниц и независимое подтверждение AI-ожиданий не входят в этот завершённый этап. Sandbox рассчитан на фиксированный набор Python-зависимостей. Отчёт враждебного проекта остаётся недоверенным наблюдением; см. `runner-security.md`. Удалённый GitHub CI не запускался, но добавлен отдельный Compose/gVisor job.
