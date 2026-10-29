import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {navigate,openDiff} from './redesign-helpers';

test('Первый визит: понятный старт на пустом состоянии, без запроса к LLM',async({page})=>{
 let external=0;await page.route('**/api/projects',r=>r.fulfill({json:[]}));await page.route('**/api/projects/*/ai-context',r=>{external++;return r.abort()});
 await page.goto('/');await expect(page.getByRole('heading',{name:'Привет! Я Дебагыч. Проверим твой код?'})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Первая проверка без сложных настроек'})).toBeVisible();
 await page.getByRole('button',{name:'Проверить проект',exact:true}).click();await expect(page.getByLabel('Название проекта')).toBeFocused();await page.keyboard.press('Escape');expect(external).toBe(0);
});

test('Вход в существующее демо работает без дублирования проекта и AI-запросов',async({page,request})=>{
 let projects=await(await request.get('/api/projects')).json();if(!projects.some((p:{demo:boolean})=>p.demo)){await request.post('/api/demo');projects=await(await request.get('/api/projects')).json()}expect(projects.some((p:{demo:boolean})=>p.demo)).toBe(true);
 let creates=0,ai=0;page.on('request',r=>{if(r.method()==='POST'&&r.url().endsWith('/api/demo'))creates++;if(r.url().endsWith('/ai-context'))ai++});
 await page.goto('/');await expect(page.getByRole('button',{name:'Попробовать демо',exact:true})).toBeEnabled();await page.getByRole('button',{name:'Попробовать демо',exact:true}).click();await expect(page.getByText('ПОДГОТОВЛЕННАЯ ДЕМОНСТРАЦИЯ',{exact:true})).toBeVisible();await expect(page).toHaveURL(/workspace\/overview\?project=/);expect(creates).toBe(0);expect(ai).toBe(0);
});

test('Мастер: код, требования, настройки, отказ от отправки данных',async({page})=>{
 // Consent UI is an explicit offline fixture, independent of developer API keys.
 await page.route('**/api/health',async route=>{const response=await route.fetch();await route.fulfill({json:{...await response.json(),ai_available:true,ai_provider_mode:'contract-test'}})});
 await page.route('**/api/projects/*/ai-context',route=>route.fulfill({json:{project_state_sha256:'offline-state',provider_fingerprint:'offline-provider',provider:'contract-test',model:'offline-test',manifest:[],max_job_usd_estimate:0}}));
 await page.route('**/api/projects/*/autonomous',route=>route.abort());
 await page.goto('/');await page.getByRole('button',{name:'Проверить проект',exact:true}).click();await page.getByLabel('Название проекта').fill('Redesign · first-use walkthrough');await page.getByRole('button',{name:'Создать проект'}).click();
 await expect(page.getByRole('button',{name:'Продолжить',exact:true})).toBeDisabled();
 await page.getByLabel('Загрузить файлы').setInputFiles({name:'calc.py',mimeType:'text/plain',buffer:Buffer.from('def add(a,b): return a-b\n')});await expect(page.getByText('calc.py',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Продолжить',exact:true}).click();await expect(page.getByRole('heading',{name:'Как должен работать ваш проект?'})).toBeVisible();await expect(page.getByRole('button',{name:'Продолжить',exact:true})).toBeDisabled();
 await page.getByLabel('Загрузить требования').setInputFiles({name:'requirements.md',mimeType:'text/markdown',buffer:Buffer.from('R1. add возвращает сумму двух аргументов.')});await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();await page.getByRole('button',{name:'Продолжить',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Рекомендуемая проверка'})).toBeVisible();await expect(page.getByRole('button',{name:'Только создать тестовый план'})).not.toBeVisible();await page.getByRole('button',{name:'Продолжить',exact:true}).click();
 let posts=0;page.on('request',r=>{if(r.url().endsWith('/autonomous')&&r.method()==='POST')posts++});
 page.once('dialog',async d=>{expect(d.message()).toContain('Резерв расходов');expect(d.message()).toContain('Передать очищенные данные');await d.dismiss()});await page.getByRole('button',{name:'Начать проверку',exact:true}).click();await expect(page.getByRole('button',{name:'Начать проверку',exact:true})).toBeEnabled();expect(posts).toBe(0);
 await page.getByRole('button',{name:'Назад',exact:true}).click();await expect(page.getByRole('heading',{name:'Рекомендуемая проверка'})).toBeVisible();
});

test('Без ключа загрузка доступна, но запуск AI остаётся заблокирован',async({page,request})=>{
 const project=await(await request.post('/api/projects',{data:{name:'No-key UI boundary'}})).json();
 await page.route('**/api/health',async route=>{const response=await route.fetch();await route.fulfill({json:{...await response.json(),ai_available:false}})});
 let calls=0;await page.route('**/api/projects/*/ai-context',route=>{calls++;return route.abort()});
 await page.goto('/#/workspace/overview?project='+project.id);
 await expect(page.getByRole('button',{name:'Запустить проверку',exact:true})).toBeDisabled();
 await expect(page.getByLabel('Загрузить файлы')).toBeEnabled();expect(calls).toBe(0);
});

test('Старые URL, project ID, Назад и выбор проекта сохраняют контекст',async({page,request})=>{
 const a=await(await request.post('/api/projects',{data:{name:'Redesign · project A'}})).json(),b=await(await request.post('/api/projects',{data:{name:'Redesign · project B'}})).json();
 await page.goto('/#/test-studio?project='+a.id);await expect(page.getByLabel('Текущий проект')).toHaveValue(a.id);await expect(page.getByRole('heading',{name:'Проверки проекта'})).toBeVisible();
 await page.getByLabel('Текущий проект').selectOption(b.id);await expect(page).toHaveURL(new RegExp(b.id));await expect(page.getByText('Redesign · project B',{exact:true}).first()).toBeVisible();await page.reload();await expect(page.getByLabel('Текущий проект')).toHaveValue(b.id);
 await navigate(page,'Отчёт');await navigate(page,'Ошибки');await page.goBack();await expect(page.getByRole('heading',{name:'Отчёт о проверке'})).toBeVisible();await expect(page.getByLabel('Текущий проект')).toHaveValue(b.id);
});

test('Смена проекта не переносит статус и завершившийся запоздалый ответ',async({page,request})=>{
 const a=await(await request.post('/api/projects',{data:{name:'Redesign · delayed A'}})).json(),b=await(await request.post('/api/projects',{data:{name:'Redesign · clean B'}})).json();
 let release!:()=>void;const blocked=new Promise<void>(r=>release=r);let intercepted=false;
 await page.route(`**/api/projects/${a.id}/files`,async r=>{intercepted=true;await blocked;await r.fulfill({json:[{id:'old-file',name:'old-project.py',size:50}]})});
 await page.goto('/#/workspace/overview?project='+a.id);await expect.poll(()=>intercepted).toBe(true);await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toBeVisible();
 await page.getByLabel('Текущий проект').selectOption(b.id);await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toHaveCount(0);release();await page.getByRole('button',{name:'Обновить',exact:true}).click();await expect(page.getByText('old-project.py',{exact:true})).toHaveCount(0);await expect(page.getByLabel('Текущий проект')).toHaveValue(b.id);await expect(page.getByRole('heading',{name:'Проверим проект за четыре шага',exact:true})).toBeVisible();
});

test('Демо: простой обзор, раскрытие кода, доказательство и безопасная проверка патча',async({page,request})=>{
 test.setTimeout(90000);
 const demo=await(await request.post('/api/demo')).json();expect(demo.demo).toBe(true);await request.post(`/api/projects/${demo.id}/analyze`);
 const terminal=async()=>{await expect.poll(async()=>{const r=await(await request.get(`/api/projects/${demo.id}/runs`)).json();return r.at(-1)?.status},{timeout:30000}).toBe('completed')};await terminal();await request.post(`/api/projects/${demo.id}/runs`);await terminal();
 await page.goto('/#/workspace/tests?project='+demo.id);await expect(page.getByRole('tab',{name:'Обзор проверки',exact:true})).toHaveAttribute('aria-selected','true');await expect(page.getByLabel('Код · pytest',{exact:true})).toHaveCount(0);await expect(page.getByRole('heading',{name:'Ожидаемый результат'})).toBeVisible();
 await page.getByRole('tab',{name:'Автотест',exact:true}).click();await expect(page.getByLabel('Код · pytest',{exact:true})).toBeVisible();await page.reload();await expect(page.getByRole('tab',{name:'Автотест',exact:true})).toHaveAttribute('aria-selected','true');
 await navigate(page,'Ошибки');await expect(page.getByLabel('Traceback',{exact:true})).not.toBeVisible();await page.getByText('Посмотреть доказательство · traceback',{exact:true}).click();await expect(page.getByLabel('Traceback',{exact:true})).toContainText('AssertionError');
 await page.getByRole('button',{name:'Предложить исправление'}).click();await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeDisabled();await openDiff(page);await expect(page.getByLabel('Diff исправления')).toContainText('+    return balance >= amount');
 await page.getByRole('button',{name:'Проверить исправление'}).click();await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeEnabled({timeout:30000});await expect(page.getByRole('cell',{name:'13 успешно / 1 с отклонением',exact:true})).toBeVisible();await expect(page.getByRole('cell',{name:'14 успешно / 0 с отклонением',exact:true})).toBeVisible();
 page.once('dialog',d=>d.dismiss());await page.getByRole('button',{name:'Подтвердить применение'}).click();await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeEnabled();const fixes=await(await request.get(`/api/projects/${demo.id}/fixes`)).json();expect(fixes.every((f:{applied:boolean})=>!f.applied)).toBe(true);
});

test('Прогресс не приписывает пропущенные этапы и чужие доказательства текущему циклу',async({page,request})=>{
 const p=await(await request.post('/api/projects',{data:{name:'Redesign · stage contract'}})).json();
 await page.route(`**/api/projects/${p.id}/runs`,r=>r.fulfill({json:[{id:'old-proof',operation:'confirm_proof',status:'completed',parent_workflow_id:'previous'},{id:'current',operation:'autonomous',status:'completed',stage:'report'}]}));await page.goto('/#/workspace/overview?project='+p.id);
 await page.getByText('Ход последней проверки',{exact:true}).click();const journey=page.getByRole('region',{name:'Ход проверки'});await expect(journey.getByText('Не потребовался',{exact:true})).toHaveCount(3);await expect(journey).not.toContainText('%');await expect(journey.getByText('Технические детали выполнения')).toBeVisible();
});

test('Старый отказ не становится текущим статусом после завершившейся повторной проверки',async({page,request})=>{
 const p=await(await request.post('/api/projects',{data:{name:'Redesign · resolved attention'}})).json();
 await page.route(`**/api/projects/${p.id}/runs`,r=>r.fulfill({json:[{id:'old',operation:'autonomous',status:'manual_review_required',stage:'generation',error:'old ambiguity'},{id:'new',operation:'autonomous',status:'completed',stage:'report'}]}));await page.goto('/#/workspace/overview?project='+p.id);await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toHaveCount(0);await expect(page.locator('.alert.warning')).toHaveCount(0);await expect(page.getByRole('heading',{name:'Нужно проверить ожидания',exact:true})).toHaveCount(0);
});

test('Без API-ключа импорт доступен, AI-запуск недоступен и это объяснено',async({page,request})=>{
 const p=await(await request.post('/api/projects',{data:{name:'Redesign · no LLM key'}})).json();await page.route('**/api/health',r=>r.fulfill({json:{status:'ok',ai_available:false,ai_status:'missing_api_key',ai_provider_mode:'openai-compatible',execution:'gvisor-python'}}));
 await page.goto('/#/workspace/overview?project='+p.id);await expect(page.getByLabel('Загрузить файлы')).toBeEnabled();await page.getByRole('button',{name:'4 Запуск',exact:true}).click();await expect(page.getByText('AI пока не настроен. Загрузка доступна без API-ключа.',{exact:true})).toBeVisible();await expect(page.getByRole('button',{name:'Начать проверку',exact:true})).toBeDisabled();
});
