# AI Companion: карта интеграции

Основа: release/redesign-2-integration, b9ac4a2. Новый worktree и ветка release/ai-companion-1. Прежние рабочие копии не изменяются.

- Данные: существующий reload/polling main.tsx. GET /api/projects/{id}/runs, /api/bugs?project_id={id}, /api/projects/{id}/fixes. Новых endpoint, SSE или таймеров прогресса нет.
- Адаптер фильтрует project_id и последнее корневое задание с его parent_workflow_id. Старые задания и ошибки предыдущего запуска не запускают реакции нового.
- Bug Proof: только confirmed/fix_verified и привязка к run_id либо bug_id текущего workflow.
- Success: fix.verified, конкретный verification_id, completed verify с совпадающими fix_id/bug_id и положительным assessment. Одних completed или passed недостаточно.
- Контекстные действия: существующие hash-маршруты Test Studio, Bug Lab, Reports и POST /api/bugs/{id}/verify-fix. Объяснения формируются из уже полученных expected/actual/steps/diff/measurement.
- MascotSlot остаётся точкой визуального расширения. Companion размещается в собственной колонке; на узком экране панель находится в потоке документа.
- У backend нет endpoint контекстного чата. Чат и дополнительные LLM-вызовы не создаются.
- 3D: проверенные interaction и bug_final из Cinematic v4; сидячая сцена для fixing. Модели копируются без изменения, SHA-256 фиксируются. Восемь лапок исходного жука сохраняются.
