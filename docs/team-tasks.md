# Параллельная работа пяти участников

Контракт API фиксируется в FastAPI OpenAPI; изменения response shape согласуются до слияния. Работайте отдельными ветками, без общих runtime volumes в тестах. Сначала добейтесь зелёного вертикального среза, затем расширяйте.

| Участник | Владение | Следующие конкретные задачи | Готово, когда |
|---|---|---|---|
| 1 · Lead / Backend | apps/api, infra/migrations | Разнести records на нормализованные таблицы, snapshots и timestamp; атомарный job guard, пагинация; auth перед внешней публикацией | Миграции up/down проверены на PostgreSQL, API сохраняет связи, конкурентные постановки не дублируют задания, OpenAPI обновлён |
| 2 · AI Engineer | services/ai | Провайдерские contract tests; требование → отдельные исполняемые тесты с source refs; LLM Failure/Fix для общего пути | Live ответы валидны, границы бюджета соблюдаются, prompt injection не меняет контракты, патч не трогает assertions; без ключа честная деградация |
| 3 · QA Automation | tests, demo, Bug Proof policy | Независимые oracle по версиям; ошибочные тесты/зависимости/timeout fixtures; browser evidence; coverage assertions | Исходная ошибка воспроизводится, исправленная версия проходит, инфраструктура не становится confirmed, screenshots/traces доступны в отчёте |
| 4 · Frontend | apps/web | Редактор с requirement navigation, browser steps и artifact viewer; stale-request protection; отмена задач после API | Все действия имеют реальные обработчики; мобильный UI и E2E проходят; результат всегда привязан к версии выбранного проекта |
| 5 · DevOps / Integration | infra, docker-compose.yml, .github | Проверить Compose на Linux, healthchecks, migration smoke, persistent queue; внешний sandbox supervisor и resource abuse tests | Одна команда поднимает всё; API/worker без socket; sandbox без секретов и исходящего интернета; CPU/RAM/PID/time limits подтверждены тестами |

## Последовательность интеграции

1. Зафиксировать и проверить текущую демонстрацию без LLM.
2. Backend + DevOps стабилизируют очередь, миграции, версии snapshot.
3. AI + QA фиксируют схемы generated plan и независимое подтверждение ожиданий.
4. DevOps выдаёт runner transport contract и работающую sandbox; только после аудита включается исполнение загрузок.
5. Frontend подключает общий Fix & Verify и browser artifacts. Затем дополнительная функциональность.

## Общее правило приёмки

PR описывает наблюдаемое изменение, выполненные проверки и ограничения. PASS только после выполнения. Demo, AI-generated, measured и unverified должны оставаться различимыми и в данных, и в UI. Патчи пользовательских проектов не применять без отдельного явного подтверждения.
