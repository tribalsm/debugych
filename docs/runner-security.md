# Модель безопасности Python Runner

Для отдельного профиля JS/TS / Playwright действуют та же gVisor-граница и data-only API, но другой фиксированный образ и лимиты Chromium. Полная модель, артефакты, ограничения и команды проверок: [javascript-playwright.md](javascript-playwright.md). Численные Python-лимиты ниже относятся к pytest-профилю.

## Граница доверия

Загруженный Python, сгенерированный/отредактированный тест, его stdout, traceback и отчёты — недоверенные данные. API и Celery worker никогда не импортируют их и не вызывают локальный subprocess для их исполнения. Демонстрационный legacy runner выполняет только неизменяемую доверенную fixture и не принимает код.

Контрольная плоскость для загрузок — `services/runner/supervisor.py`. Это доверенный сервис с Docker authority через Unix socket. Он не имеет DB/Redis/LLM credentials. API, worker, web и sandbox не имеют socket. API может читать health supervisor; только worker получает отдельный токен для `/execute`. Supervisor находится во внутренней сети execution и не публикует порт.

Docker authority равна административной власти над Docker-хостом. Для публичного сервиса supervisor должен работать на выделенной runner VM, а не на общем production Docker-хосте. Текущая поставка предназначена для локальной команды; app auth / quotas ещё не реализованы.

## Доставка задания

1. API создаёт неизменяемый снимок: только `.py` исходники, pytest-код, UUID тестов и требований. Проверяет относительные пути, дубликаты, синтаксис тестов, размер.
2. Снимок и его SHA256 сохраняются в PostgreSQL, UUID job отправляется через Redis/Celery.
3. Worker читает ровно сохранённый снимок и передаёт JSON supervisor. Bearer token генерируется при первом Compose startup в отдельный named volume и не попадает в snapshot.
4. Pydantic запрещает неизвестные поля. Передать Docker image, runtime, shell command, mounts, environment, privileged и Docker options невозможно.
5. Supervisor разрешает только зарегистрированный `runsc` и заранее собранный образ, разрешённый оператором. Tag сначала разрешается в immutable image ID, и контейнер создаётся по этому ID. При отсутствии runtime/образа — закрытый отказ; fallback на runc/subprocess отсутствует.
6. Вход передаётся одной ограниченной JSON-строкой через stdin Docker attach. Нет tar extraction, host bind mounts или передачи source paths хостовым shell tools.

## Политика контейнера

| Граница | Настройка |
|---|---|
| Runtime | Обязательный gVisor `runsc`, константа в supervisor |
| Пользователь | UID/GID 10000, root escalation недоступен |
| Сеть | `network_mode=none`, без attached networks, без DNS / egress / управляющих портов |
| Файловая система | Read-only rootfs; `/tmp` tmpfs 96 МБ, nosuid/nodev/noexec; host mounts отсутствуют |
| Полномочия | `cap_drop=ALL`, `no-new-privileges=true`; Docker privileged не используется |
| Память | 384 MiB, memory-swap равен memory, дополнительный swap запрещён |
| CPU | 1 CPU суммарно на контейнер; RLIMIT_CPU 25 с на процесс |
| Процессы | 128 host tasks для runtime, RLIMIT_NPROC 16 guest processes |
| Дескрипторы / файлы | RLIMIT_NOFILE 128, RLIMIT_FSIZE 1 МБ, core dumps отключены |
| Время | Pytest subprocess timeout 30 с; supervisor wall wait 45 с; janitor deadline 75 с |
| Логи / результат | Docker log rotation 1 МБ; вход и выход ограничены схемой и размерами |
| Параллелизм | Два задания supervisor; Celery concurrency 2 |

`noexec` на tmpfs не запрещает интерпретатору читать Python и не считается sandbox само по себе. Главная граница — gVisor плюс отсутствие полномочий и доступа к хосту. `-I` и read-only `/opt/pytest_bootstrap.py` загружают pytest/coverage до добавления project path, предотвращая простую подмену launcher через загруженный `coverage.py`, `pytest.py` или `sitecustomize.py`.

Пакеты не устанавливаются из проекта, сеть не открывается для pip. Поддержка дополнительных зависимостей требует проверенного образа. Ошибки зависимостей / collection показываются как инфраструктурные, не BugFinding Confirmed.

## Результаты не равны доказанной корректности

Supervisor валидирует JSON, значения метрик, число кейсов и связь case → submitted test UUID, пересчитывает passed/failed/errors/skipped по кейсам и добавляет собственные SHA256/runtime/image ID. Запрещает автоматическое повышение AI assertion до Confirmed.

Внутри sandbox проект может быть намеренно враждебным: monkeypatch, подмена собственных артефактов, прямой выход процесса. Отчёты этой среды не являются криптографически доверенным oracle. `report_trust=untrusted-project-observation` явно сохраняет это ограничение. Для загрузок теперь доступны Confirmed после явной проверки ожидания пользователем и повторного gVisor-прогона, затем Fix Verified после baseline/focused/regression. Это не независимый автоматический oracle. Детали и защита применения: `fix-and-verify.md`.

Если тест изменён после отправки snapshot, результат остаётся в исходном запуске и не перезаписывает result новой версии теста. Исходники пользователя во время запуска не изменяются.

## Очистка

Каждый контейнер имеет случайное имя, UUID job, ownership label и deadline. В `finally` вызывается `remove(force=True, v=True)`. Отдельный janitor удаляет только контейнеры с ownership label после deadline, включая оставшиеся после аварийного завершения supervisor. Нет общих writable volumes между заданиями; tmpfs исчезает вместе с контейнером.

## Реально выполненные проверки

`tests/compose/sandbox_probe.py`:

- Неверный/отсутствующий токен → 401; поле `privileged` при корректном токене → 422.
- Docker inspect подтверждает runtime, user policy, rootfs, network, RAM/swap, CPU, PID; bind mounts отсутствуют.
- Внутри gVisor: UID 10000, нет socket/секретов/volume данных; setuid(0), запись `/etc` и `/opt` отклоняются; внешний connect невозможен; CapEff=0, NoNewPrivs=1.
- RLIMIT_NPROC реально блокирует дальнейшие fork, дочерние процессы убираются.
- Выделение 600 МБ вызывает OOM kill контейнера, фиксируется exit 137 / OOMKilled=true.
- Sleep 100 с прерывается harness через ~30 с; инфраструктурный failure, не подтверждённый дефект.
- После каждого прогона проверяется отсутствие оставшихся sandbox-контейнеров.

Это проверка перечисленных границ, а не аудит всех возможных побегов из gVisor и не гарантия отсутствия runtime/kernel уязвимостей. Хост и runtime должны обновляться. Официальные инструкции: [установка gVisor](https://gvisor.dev/docs/user_guide/install/), [Docker runtime](https://gvisor.dev/docs/user_guide/quick_start/docker/).
