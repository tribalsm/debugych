# Проверка JavaScript / TypeScript и Playwright

Дата: 19 октября 2026. Реальный локальный Docker Compose на WSL Ubuntu, PostgreSQL, Redis, Celery и обязательный gVisor `runsc`.

## Выполненные проверки

- `python -m pytest -q`: **78 passed**, 10.25 с. Предупреждение Starlette TestClient о deprecated AnyIO alias не влияет на результат.
- Production frontend: TypeScript compile + Vite build прошли; Compose `up --build -d --wait` поднял все сервисы, init-контейнеры завершились с кодом 0.
- `COMPOSE_CONTRACT_TEST=1 PLAYWRIGHT_BASE_URL=http://127.0.0.1:8080 npm run test:e2e`: **8 passed**, 49.0 с. Включён один намеренно ожидаемый assertion failure доверенного Shop; это успешная проверка воспроизведения исходного дефекта.
- `python tests/compose/playwright_smoke.py`: загружены и реально выполнены **JavaScript и TypeScript** проекты. В каждом — **2 passed / 1 failed**, три PNG 960×640, JSON Playwright report, Istanbul coverage map. Дефект счётчика: кнопка уменьшает значение до −1 вместо увеличения до 1. Никаких подставных результатов браузера нет.
- Повтор Bug Proof каждого JS/TS-проекта выполнялся в новом runsc-контейнере с тем же image ID. После ручного review и совпадения статусов получен Confirmed. Предложение Python-патча для браузерного проекта отклонено 409.
- Загруженные package scripts с `exit 77/78`, неподдерживаемая dependency и бросающий исключение `playwright.config.js` не запускались. Тестируемый локальный сайт успешно собирался по фиксированному контракту.
- Ошибка синтаксиса сгенерированного TypeScript возвращает failed collection run; runtime page error даёт error case даже при успешном assertion. Оба сценария не создают новый product bug. Старые артефакты скачиваются после правок; SHA256 совпадает.
- `tests/compose/react_smoke.py` через supervisor: **1 passed** — реальные React 19, TSX, импорт CSS, computed CSS assertion, PNG и measured coverage проекта. Зависимости исключены из покрытия.
- `tests/compose/playwright_probe.py`: non-root UID 10000, отсутствие credentials/Docker socket/token/host IPC, запрет записи в образ, нулевые effective capabilities, невозможность внешнего TCP и browser navigation, фиксированные cgroup параметры. Зависший JS worker прерван через global deadline около 35 с; статус failed, контейнер удалён.
- Повтор `tests/compose/sandbox_probe.py`: прежние Python-проверки auth, запрета произвольных Docker options и подмены image ID, filesystem/network/NPROC, настоящего OOM exit 137, 30-секундного timeout и cleanup прошли.
- Прежний API smoke Python Fix & Verify и браузерный Python-путь проходят: baseline 2/1, целевой тест 1/0, полный набор 3/0, отказ на регрессию/устаревшее состояние, отдельное подтверждение применения.
- После удаления тестового провайдера обычный Compose healthy: `ai_available=false`, `ai_provider_mode=live`, `playwright_available=true`. Сохранённый Playwright-план повторно выполнен **без LLM-ключа**: 2 passed / 1 failed, 3 PNG с проверенными hash. Изменение IP API после пересоздания корректно подхвачено Nginx.

## Проверки контрактов и хранения

Новые unit/integration проверки покрывают JS/TS upload как UTF-8 данные, привязку языка к профилю, обязательный index.html, запрет неизвестных профилей и команд, assertion vs infrastructure classification; PNG type/signature/dimensions/chunks/CRC, JSON и размер; безопасные имена; выдачу только по правильной паре run/artifact UUID; 404 для чужого запуска, 422 для неверного UUID и 409 после изменения сохранённого blob. В JSON run хранятся метаданные, а не base64.

Браузерный E2E проходит создание проекта → загрузку TS/HTML/требований → AI-план → реальный gVisor run → три загруженных PNG → скачивание отчёта → measured coverage в Reports → Reproduced в Bug Lab. Прежние проверки Dashboard, мобильного UI, stale project selection и отдельного подтверждения apply сохранены.

## Честные границы

Внешний LLM в сквозных тестах заменён **явно включённым контрактным провайдером**; это подготовленные AI-ответы. API, очередь, браузер, исполнение, скриншоты и покрытие реальны. Живой LLM без пользовательского ключа не проверялся. Тестовый override исключён из обычного Compose.

Профиль поддерживает локальное браузерное приложение с root `index.html`, JS/TS/JSX/TSX, CSS/JSON и фиксированными библиотеками. Произвольные Node backends, npm installation и пользовательские команды не поддерживаются. TypeScript транспилируется, но `tsc`-проверка типов и source-map coverage не заявляются. Покрытие относится к скомпилированным JS-модулям проекта. Trace/video и JS/TS Fix & Verify остаются будущей работой. Внешние файлы/интернет не нужны для исполнения; браузерные бинарники устанавливаются при сборке образа.

Артефакты — наблюдения из недоверенного контейнера, а не независимое доказательство корректности. Hash защищает сохранённый blob от последующих изменений, не от вмешательства тестируемого кода до сохранения.

Локальный CI workflow дополнен smoke/probes; удалённый GitHub CI в этой сессии не запускался. Протокол и точные лимиты описаны в `javascript-playwright.md`. Примеры результатов: `playwright-result.json`, `react-probe-result.json`, `playwright-probes.log`, `browser-failure.png`, `playwright-reports.png` в пакете outputs.
