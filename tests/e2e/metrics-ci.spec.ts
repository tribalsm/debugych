import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {navigate} from './redesign-helpers';
import fs from 'node:fs/promises';

test('Метрики и CI-экспорт на фактическом демопрогоне без новой AI-генерации',async({page,request})=>{
 const project=await(await request.post('/api/demo')).json();
 const wait=async(id:string)=>{await expect.poll(async()=>{const r=await(await request.get('/api/runs/'+id)).json();return r.status},{timeout:45000}).toBe('completed')};
 await wait((await(await request.post(`/api/projects/${project.id}/analyze`)).json()).id);
 await wait((await(await request.post(`/api/projects/${project.id}/runs`)).json()).id);
 await page.goto('/#/workspace/report?project='+project.id);
 const metrics=page.getByRole('region',{name:'Метрики успешности тестирования'});
 await expect(metrics).toContainText('92.9%');await expect(metrics).toContainText('0.0%');
 await page.getByLabel('Период метрик').selectOption('all');await expect(metrics).toContainText('1 завершённых попыток');
 let pending=page.waitForEvent('download');await page.getByRole('button',{name:'JUnit XML',exact:true}).click();const xml=await pending;
 expect(xml.suggestedFilename()).toBe('debugych-junit.xml');const contents=await fs.readFile((await xml.path())!,'utf8');expect(contents).toContain('<failure');expect(contents).toContain('tests="14"');
 pending=page.waitForEvent('download');await page.getByRole('button',{name:'GitHub Actions .zip'}).click();const archive=await pending;
 expect(archive.suggestedFilename()).toBe('debugych-ci.zip');expect((await fs.readFile((await archive.path())!)).subarray(0,2).toString()).toBe('PK');
 await page.setViewportSize({width:390,height:844});await expect(metrics).toBeVisible();expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await navigate(page,'Тесты');await expect(page.getByRole('button',{name:'Запустить тесты',exact:true})).toBeVisible();
});
