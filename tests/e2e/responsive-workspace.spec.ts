import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {responsiveFixture} from './fixtures/responsive-fixture.cjs';

const sizes=[[320,844],[360,800],[390,844],[430,932],[768,1024],[844,390],[1024,600],[1024,900],[1280,800],[1440,900],[1920,1080]];
for(const [width,height] of sizes)test(`Responsive QA workspace ${width}x${height}: code, proof, diff and report`,async({page})=>{
 await page.setViewportSize({width,height});
 const data=responsiveFixture(true);let writes=0;
 await page.route('**/api/**',async route=>{
  if(route.request().method()!=='GET'){writes++;return route.abort()}
  const u=new URL(route.request().url()),value=data.routes[u.pathname+u.search];
  await route.fulfill({status:value===undefined?404:200,json:value??{detail:'Fixture route missing'},headers:{'X-Debugych-Public-Demo':'1'}});
 });
 const noPageOverflow=async()=>expect(await page.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
 await page.goto('/#/workspace/overview?project='+data.projectId);
 await expect(page.getByRole('heading',{name:data.routes['/api/projects'][0].name,exact:true})).toBeVisible();
 await noPageOverflow();
 await page.goto('/#/workspace/tests?project='+data.projectId);
 await expect(page.getByRole('heading',{name:'Тестовый набор',exact:true})).toBeVisible();
 await noPageOverflow();
 if(width<=430){
  const guest=page.getByRole('button',{name:'Загрузить свой проект без регистрации'}),bounds=await guest.boundingBox();
  expect(bounds!.x+bounds!.width).toBeLessThanOrEqual(await page.evaluate(()=>document.documentElement.clientWidth));
 }
 await page.getByRole('tab',{name:'Автотест',exact:true}).click();
 const code=page.getByLabel('Код · pytest',{exact:true});
 await expect(code).toContainText('SYNTHETIC RESPONSIVE FIXTURE');
 expect((await code.boundingBox())!.height).toBeLessThanOrEqual(height*.65+2);
 expect(await code.evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
 await code.press('ArrowRight');await expect.poll(()=>code.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
 await noPageOverflow();
 await page.getByRole('tab',{name:'Автотест',exact:true}).press('ArrowLeft');
 await expect(page.getByRole('tab',{name:'Gherkin',exact:true})).toHaveAttribute('aria-selected','true');
 await page.getByRole('button',{name:'Ошибки',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Воспроизводимое доказательство'})).toBeVisible();
 await noPageOverflow();
 await page.getByText('Посмотреть доказательство · traceback',{exact:true}).click();
 await expect(page.getByLabel('Traceback',{exact:true})).toContainText('SYNTHETIC TRACEBACK');
 await page.getByText('Посмотреть предлагаемые изменения · diff',{exact:true}).click();
 const diff=page.getByLabel('Diff исправления',{exact:true});
 expect(await diff.evaluate(e=>e.scrollWidth>e.clientWidth)).toBe(true);
 await diff.press('ArrowRight');await expect.poll(()=>diff.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
 const table=page.getByRole('region',{name:'Сравнение результатов до и после исправления'});
 await expect(table).toHaveAttribute('tabindex','0');
 if(await table.evaluate(e=>e.scrollWidth>e.clientWidth)){
  await table.press('ArrowRight');await expect.poll(()=>table.evaluate(e=>e.scrollLeft)).toBeGreaterThan(0);
 }
 await expect(page.getByRole('button',{name:'Подтвердить применение',exact:true})).toBeDisabled();
 await noPageOverflow();
 await page.getByRole('button',{name:'Отчёт',exact:true}).click();
 await expect(page.getByRole('heading',{name:'Успешность тестирования'})).toBeVisible();
 await expect(page.getByRole('region',{name:'Таблица истории заданий'})).toHaveAttribute('tabindex','0');
 await noPageOverflow();expect(writes).toBe(0);
});
