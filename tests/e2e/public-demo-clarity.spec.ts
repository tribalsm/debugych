import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Public snapshot offers a clear read-only journey without owner or LLM setup claims',async({page})=>{
 const project='public-control',bug='public-bug',fix='public-fix';let writes=0;
 await page.route('**/api/**',async route=>{
  const req=route.request(),url=new URL(req.url());
  if(req.method()!=='GET'){writes++;return route.abort()}
  const json=url.pathname==='/api/health'?{ai_available:false,execution:'gvisor-python',ai_provider_mode:'unavailable',ai_status:'public demo',guest_mode_available:true}:
   url.pathname==='/api/projects'?[{id:project,name:'Public control',demo:false,created_at:'2026-10-28T12:00:00Z'}]:
   url.pathname.endsWith('/runs')?[{id:'public-run',operation:'run',status:'completed',passed:1,failed:1,errors:0,created_at:'2026-10-28T12:00:00Z',cases:[{name:'sum',status:'failed',traceback:'AssertionError'},{name:'zero',status:'passed',traceback:''}]}]:
   url.pathname.endsWith('/test-cases')?[{id:'public-test',framework:'pytest',title:'Addition',requirement_key:'R1',code:'assert add(2,3)==5',gherkin:'Scenario: Addition',status:'validated'}]:
   url.pathname.endsWith('/ai-statistics')?{attempts:0,succeeded:0,failed:0,reserved_tokens:0,reserved_cost_micro_usd:0,provider_usage_available:0,notice:'Prepared fixture',calls:[]}:
   url.pathname==='/api/bugs'?[{id:bug,title:'Addition',status:'fix_verified',requirement:'R1',file:'calc.py',expected:'Return sum',actual:'Returns difference',traceback:'AssertionError',steps:[],code:'assert add(2,3)==5',description:'Control',recommendation:'Review patch',current_fix_id:fix}]:
   url.pathname.endsWith('/fixes')?[{id:fix,bug_id:bug,diff:'--- a/calc.py\n+++ b/calc.py\n- return a-b\n+ return a+b',verified:true,applied:false,explanation:'Offline control patch'}]:[];
  await route.fulfill({json,headers:{'X-Debugych-Public-Demo':'1'}});
 });
 await page.goto('/');
 await expect(page.getByText('Сохранённая демонстрация',{exact:false})).toBeVisible();
 await expect(page.getByRole('button',{name:'Новый проект',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Проверить проект',exact:true})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Загрузить свой проект без регистрации'})).toBeVisible();
 await page.getByRole('button',{name:'Мои проекты',exact:true}).click();
 await page.getByRole('button',{name:'Открыть демо',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Сохранённая проверка',exact:true})).toBeVisible();
 await expect(page.getByRole('heading',{name:'Подготовка проекта',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Ошибки',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Воспроизводимое доказательство'})).toBeVisible();
 await expect(page.getByText('Сохранённое предложение',{exact:false})).toBeVisible();
 await expect(page.getByText('Для нового предложения настройте LLM_API_KEY.',{exact:false})).toHaveCount(0);
 await expect(page.getByRole('button',{name:'Подтвердить применение',exact:true})).toBeDisabled();
 await page.getByRole('button',{name:'Отчёт',exact:true}).click();
 await expect(page.locator('.testing-success')).toHaveCSS('padding','24px');
 await expect(page.getByRole('button',{name:'.feature',exact:true})).toBeDisabled();
 await page.setViewportSize({width:390,height:844});
 await expect(page.locator('.testing-success')).toHaveCSS('padding','16px');
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=document.documentElement.clientWidth)).toBe(true);
 expect(writes).toBe(0);
});

test('Changing project clears an old proof target while foreign direct links remain rejected',async({page})=>{
 const first='11111111-1111-4111-8111-111111111111',second='22222222-2222-4222-8222-222222222222',bug='33333333-3333-4333-8333-333333333333';
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),pathname=url.pathname;
  const json=pathname==='/api/health'?{ai_available:false,execution:'gvisor-python',workspace_mode:'account'}:
   pathname==='/api/projects'?[{id:first,name:'First project',demo:false,created_at:'2026-10-28T12:00:00Z'},{id:second,name:'Second project',demo:false,created_at:'2026-10-28T12:00:00Z'}]:
   pathname==='/api/bugs'&&url.searchParams.get('project_id')===first?[{id:bug,title:'First proof',status:'confirmed',requirement:'R1',file:'app.py',expected:'Sum',actual:'Difference',traceback:'AssertionError',steps:[],code:'assert add(2,3)==5'}]:[];
  await route.fulfill({json});
 });
 await page.goto(`/#/workspace/bugs?project=${first}&bug=${bug}&section=proof`);
 await expect(page.getByRole('heading',{name:'Воспроизводимое доказательство'})).toBeVisible();
 await page.getByLabel('Текущий проект',{exact:true}).selectOption(second);
 await expect(page).toHaveURL(new RegExp('project='+second+'$'));
 await expect(page.getByText('Результат по ссылке не найден в выбранном проекте.',{exact:false})).toHaveCount(0);
 await expect(page.getByRole('heading',{name:'Воспроизводимое доказательство'})).toHaveCount(0);
 await page.goto(`/#/workspace/bugs?project=${second}&bug=${bug}&section=proof`);
 await expect(page.getByRole('alert')).toContainText('Результат по ссылке не найден');
});

test('Uploaded tests do not claim measured coverage of documented requirements',async({page})=>{
 const project='uploaded-control';
 await page.route('**/api/**',async route=>{
  const pathname=new URL(route.request().url()).pathname;
  const json=pathname==='/api/health'?{ai_available:false,execution:'gvisor-python',workspace_mode:'account'}:
   pathname==='/api/projects'?[{id:project,name:'Uploaded control',demo:false,created_at:'2026-10-28T12:00:00Z'}]:
   pathname.endsWith('/runs')?[{id:'uploaded-run',operation:'run',status:'completed',passed:1,failed:0,errors:0,quality:{observation_valid:true,requirements:{total:1,exercised:['USER_TESTS'],exercise_ratio:1},negative_requirements_claimed_and_executed:[]}}]:
   pathname.endsWith('/test-cases')?[{id:'uploaded-test',title:'test_math.py',framework:'pytest',origin:'uploaded-user-tests',requirement:'USER_TESTS',code:'assert 2+3==5',gherkin:'Scenario: Uploaded',result:'passed'}]:
   pathname.endsWith('/ai-statistics')?{attempts:0,succeeded:0,failed:0,reserved_tokens:0,reserved_cost_micro_usd:0,provider_usage_available:0,calls:[],notice:'No AI calls'}:[];
  await route.fulfill({json});
 });
 await page.goto('/#/workspace/report?project='+project);
 await expect(page.getByText('Тесты загружены пользователем. Соответствие документу требований не проверено; покрытие требований не рассчитывается.',{exact:true})).toBeVisible();
 await expect(page.getByText('требований связаны с выполненными assertions',{exact:false})).toHaveCount(0);
});
