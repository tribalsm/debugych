import {navigate,openAnalytics} from './redesign-helpers';
import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import AxeBuilder from '../../apps/web/node_modules/@axe-core/playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const output=path.resolve(process.cwd(),'../../outputs/uiux-after');
async function project(request:any,name:string){const response=await request.post('/api/projects',{data:{name}});expect(response.ok()).toBeTruthy();return (await response.json()).id as string}
async function selectProject(page:any,id:string){await page.goto('/#/workspace/overview');await page.getByLabel('Текущий проект').selectOption(id);await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toHaveCount(0)}

test('Навигация: адрес, Назад, перезагрузка, вкладки и клавиатура диалога',async({page,request})=>{
 const id=await project(request,'UIUX · keyboard');await selectProject(page,id);
 const opener=page.getByRole('button',{name:'Новый проект'});await opener.click();
 const dialog=page.getByRole('dialog',{name:'Новый проект'});await expect(page.getByLabel('Название проекта')).toBeFocused();
 await page.keyboard.press('Shift+Tab');await expect(dialog.getByRole('button',{name:'Закрыть',exact:true})).toBeFocused();
 await page.keyboard.press('Shift+Tab');await expect(page.getByLabel('Требования нового проекта')).toBeFocused();
 await page.keyboard.press('Tab');await expect(dialog.getByRole('button',{name:'Закрыть',exact:true})).toBeFocused();
 await page.keyboard.press('Tab');await expect(page.getByLabel('Название проекта')).toBeFocused();
 await page.keyboard.press('Escape');await expect(dialog).toHaveCount(0);await expect(opener).toBeFocused();
 await navigate(page,'Мои проекты');await expect(page).toHaveURL(/#\/projects$/);
 await page.goto('/#/workspace/report?project='+id);await page.goBack();await expect(page.getByRole('heading',{name:'Ваши проекты'})).toBeVisible();
 await page.reload();await expect(page.getByRole('heading',{name:'Ваши проекты'})).toBeVisible();
 await page.getByRole('button',{name:'Уменьшить движение'}).click();await expect(page.locator('.app')).toHaveClass(/reduce-motion/);await page.reload();await expect(page.locator('.app')).toHaveClass(/reduce-motion/);await navigate(page,'Главная');await page.getByRole('button',{name:'Отключить реплики',exact:true}).click();await expect(page.getByRole('heading',{name:'Проверьте проект по требованиям',exact:true})).toBeVisible();
});

test('Ошибки реальной загрузки и частично загруженный набор видны пользователю',async({page,request})=>{
 const id=await project(request,'UIUX · rejected upload');await selectProject(page,id);await navigate(page,'Мои проекты');await navigate(page,'Рабочая область');
 await page.getByLabel('Загрузить файлы').setInputFiles([{name:'requirements.md',mimeType:'text/plain',buffer:Buffer.from('R1. Valid requirements.')},{name:'bad.zip',mimeType:'application/zip',buffer:Buffer.from('not a zip file')}]);
 await expect(page.getByRole('alert')).toContainText('bad.zip');await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();
 await page.getByLabel('Загрузить файлы').setInputFiles({name:'oversize.py',mimeType:'text/plain',buffer:Buffer.alloc(10*1024*1024+1,32)});
 await expect(page.getByRole('alert')).toContainText('10 МБ');
 await page.getByLabel('Загрузить файлы').setInputFiles({name:'valid.py',mimeType:'text/plain',buffer:Buffer.from('def add(a,b): return a+b')});await expect(page.getByText('valid.py',{exact:true})).toBeVisible();
});

test('Сетевой сбой не превращается в пустой успешный экран; повторное подключение',async({page})=>{
 await page.route('**/api/projects',route=>route.fulfill({status:503,json:{detail:'UI contract: API временно недоступен'}}));await page.goto('/');await expect(page.getByRole('alert')).toContainText('API временно недоступен');
 await page.unroute('**/api/projects');await page.getByRole('button',{name:'Повторить подключение'}).click();await expect(page.getByRole('alert')).toHaveCount(0);await expect(page.getByRole('heading',{name:'Привет! Я Дебагыч. Проверим твой код?'})).toBeVisible();
});

test('Явный UI-контракт: стадии задачи, infrastructure и manual review не становятся дефектом',async({page,request})=>{
 const id=await project(request,'UIUX · task state contract');let status='running',stage='generation';
 await page.route(`**/api/projects/${id}/runs`,route=>route.fulfill({json:[{id:'fixture-run',operation:'autonomous',status,stage,error:status==='manual_review_required'?'ambiguous_requirement':status==='failed'?'infrastructure_failure':undefined,classification:status==='manual_review_required'?'ambiguous_requirement':undefined,validation:status==='manual_review_required'?{status:'manual_review_required',classification:'ambiguous_requirement'}:undefined}]}));
 await selectProject(page,id);await expect(page.locator('.processing')).toContainText('generation');stage='execution';await expect(page.locator('.processing')).toContainText('execution');
 status='manual_review_required';await expect(page.getByText(/Manual Review Required: автоматическая проверка остановлена/)).toBeVisible();await expect(page.locator('.processing')).toHaveCount(0);await navigate(page,'Тесты');await expect(page.getByRole('heading',{name:'Проверка генерации',exact:true})).toBeVisible();
 status='failed';await page.getByRole('button',{name:'Обновить',exact:true}).click();await expect(page.getByText(/это не подтверждённый дефект/)).toBeVisible();await navigate(page,'Ошибки');await expect(page.getByText('Нет воспроизведённых проблем.',{exact:false})).toBeVisible();
});

test('Пять экранов: реальные демопрогоны, desktop/mobile, a11y, экспорт, скриншоты',async({page,request})=>{
 test.setTimeout(120000);await fs.mkdir(output,{recursive:true});
 // Trusted demo is explicit prepared data; its runner produces real pytest observations.
 const demo=await (await request.post('/api/demo')).json();await request.post(`/api/projects/${demo.id}/analyze`);
 await expect.poll(async()=>{const runs=await (await request.get(`/api/projects/${demo.id}/runs`)).json();return runs.at(-1)?.status}).toBe('completed');
 await request.post(`/api/projects/${demo.id}/runs`);await expect.poll(async()=>{const runs=await (await request.get(`/api/projects/${demo.id}/runs`)).json();return runs.at(-1)?.status},{timeout:30000}).toBe('completed');
 const bugs=await (await request.get(`/api/bugs?project_id=${demo.id}`)).json();expect(bugs[0].status).toBe('confirmed');
 await request.post(`/api/bugs/${bugs[0].id}/propose-fix`);await expect.poll(async()=>{const runs=await (await request.get(`/api/projects/${demo.id}/runs`)).json();return runs.at(-1)?.status}).toBe('completed');
 await request.post(`/api/bugs/${bugs[0].id}/verify-fix`);await expect.poll(async()=>{const runs=await (await request.get(`/api/projects/${demo.id}/runs`)).json();return runs.at(-1)?.status},{timeout:30000}).toBe('completed');
 await page.setViewportSize({width:1440,height:1000});await selectProject(page,demo.id);
 await navigate(page,'Тесты');await expect(page.getByRole('heading',{name:'Границы оплаты, скидки и количества',exact:true})).toBeVisible();
 // Selecting the already active project must not erase its loaded tests.
 await page.getByLabel('Текущий проект').selectOption(demo.id);await expect(page.getByRole('heading',{name:'Границы оплаты, скидки и количества',exact:true})).toBeVisible();
 const screens=[['Главная','Привет! Я Дебагыч. Проверим твой код?'],['Мои проекты','Ваши проекты'],['Обзор','Shop API · граничные значения'],['Тесты','Проверки проекта'],['Ошибки','Найденные ошибки'],['Отчёт','Отчёт о проверке']];
 const violations:unknown[]=[];
 for(const [i,[name,heading]] of screens.entries()){
  await navigate(page,name);await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible();
  await page.screenshot({path:path.join(output,`${i+1}-${name.toLowerCase().replaceAll(' ','-')}-desktop.png`),fullPage:true,animations:'disabled'});
  const audit=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa','wcag22aa']).analyze();violations.push(...audit.violations.map(v=>({page:name,id:v.id,impact:v.impact,nodes:v.nodes.map(n=>n.target)})));
 }
 await fs.writeFile(path.join(output,'accessibility.json'),JSON.stringify(violations,null,2));expect(violations).toEqual([]);
 await navigate(page,'Тесты');await page.getByRole('tab',{name:'Gherkin',exact:true}).click();await page.getByRole('tab',{name:'Gherkin',exact:true}).focus();await page.keyboard.press('ArrowRight');await expect(page.getByRole('tab',{name:'Автотест',exact:true})).toBeFocused();await expect(page.getByLabel('Код · pytest',{exact:true})).toBeVisible();await page.reload();await expect(page.getByRole('tab',{name:'Автотест',exact:true})).toHaveAttribute('aria-selected','true');
 await navigate(page,'Отчёт');await openAnalytics(page);await expect(page.getByRole('heading',{name:'AI Engine · журнал генераций'})).toBeVisible();await openAnalytics(page);await expect(page.getByRole('heading',{name:'AI Engine · журнал генераций'})).toBeVisible();const downloaded=page.waitForEvent('download');await page.getByRole('button',{name:'QA-отчёт .json'}).click();const download=await downloaded;const data=JSON.parse(await fs.readFile((await download.path())!,'utf-8'));expect(data.project.id).toBe(demo.id);expect(data.tests.length).toBeGreaterThan(0);expect(data.runs.some((r:any)=>r.failed===1)).toBeTruthy();
 await page.setViewportSize({width:390,height:844});await page.emulateMedia({reducedMotion:'reduce'});
 for(const [i,[name,heading]] of screens.entries()){
  await page.getByRole('button',{name:'Меню',exact:true}).click();await navigate(page,name);await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBeTruthy();
  await page.screenshot({path:path.join(output,`${i+1}-${name.toLowerCase().replaceAll(' ','-')}-mobile.png`),fullPage:true,animations:'disabled'});
 }
});
