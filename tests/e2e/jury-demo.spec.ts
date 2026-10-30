import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {readFileSync} from 'node:fs';
import path from 'node:path';
const snapshot=JSON.parse(readFileSync(path.resolve(__dirname,'../../infra/server/public-demo.json'),'utf8'));
for(const width of [390,1280])test(`Jury demo ${width}: measured controls, proof and historical AI without writes`,async({page})=>{
 await page.setViewportSize({width,height:900});let writes=0;
 await page.route('**/api/**',async route=>{if(route.request().method()!=='GET'){writes++;return route.abort()}const u=new URL(route.request().url()),value=snapshot.routes[u.pathname+u.search];await route.fulfill({status:value===undefined?404:200,json:value??{detail:'Not public'},headers:{'X-Debugych-Public-Demo':'1'}})});
 await page.goto('/');await expect(page.getByRole('heading',{name:'Как AI создавал тесты и исправления'})).toBeVisible();
 await expect(page.getByRole('link',{name:'API',exact:true})).toHaveCount(0);
 await page.getByRole('button',{name:'Открыть записи настоящих AI-прогонов'}).click();
 await expect(page.getByText('До этих успешных записей две Python workflow-попытки',{exact:false})).toBeVisible();
 await page.getByText('Python · gpt-6-luna · 20.10.2026',{exact:true}).click();
 await expect(page.getByText('provider_transport_temporary',{exact:false})).toBeVisible();
 await expect(page.getByText('LLM-запросов в этой записи: 5; ошибочных: 1.',{exact:false})).toBeVisible();
 for(const project of snapshot.routes['/api/projects'].slice(0,2)){
  await page.goto('/#/workspace/report?project='+project.id);
  await expect(page.getByRole('heading',{name:'Результаты проверки',exact:true})).toBeVisible();
  const last=snapshot.routes['/api/projects/'+project.id+'/runs'].at(-1);
  expect(last.runtime).toBe('runsc');expect(last.coverage.totals.percent_covered).toBeLessThan(100);expect(last.coverage.totals.num_branches).toBeGreaterThan(0);
  const file=project.name.startsWith('Python')?'shipping.py':'rules.ts';await page.getByText(file,{exact:true}).click();
  await expect(page.locator('.coverage-detail details').filter({has:page.getByText(file,{exact:true})}).getByText('Не покрыты:',{exact:false})).not.toContainText('нет');
  if(file==='rules.ts')await expect(page.getByText('Istanbul · исходные JS/TS/TSX',{exact:false})).toBeVisible();
  await page.getByRole('button',{name:'Ошибки',exact:true}).click();await expect(page.getByRole('heading',{name:'Воспроизводимое доказательство'})).toBeVisible();
  await page.getByText('Посмотреть предлагаемые изменения · diff',{exact:true}).click();await expect(page.getByLabel('Diff исправления',{exact:true})).toContainText('>= 500');
  await expect(page.getByRole('button',{name:'Подтвердить применение',exact:true})).toBeDisabled();
  expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
 }
 expect(writes).toBe(0);
});
