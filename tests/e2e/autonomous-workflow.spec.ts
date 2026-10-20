import {navigate,startFullQA} from './redesign-helpers';
import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Автономный QA: одно согласие → проверенный патч без ручного review и применения',async({page,request})=>{
 test.setTimeout(120000);
 test.skip(process.env.COMPOSE_CONTRACT_TEST!=='1','Explicit offline provider required');
 expect((await (await request.get('/api/health')).json()).ai_provider_mode).toBe('contract-test');
 await page.goto('/');await page.getByRole('button',{name:'Новый проект'}).click();
 await page.getByLabel('Название проекта').fill('Autonomous browser control');
 await page.getByRole('button',{name:'Создать проект'}).click();
 await page.getByLabel('Загрузить файлы').setInputFiles([
  {name:'calc.py',mimeType:'text/plain',buffer:Buffer.from('def add(a,b): return a-b\n')},
  {name:'requirements.md',mimeType:'text/plain',buffer:Buffer.from('R1. Функция add возвращает сумму a и b. CONTRACT_FALSE_REVIEW')}
 ]);
 await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();
 let dialogs=0;page.on('dialog',async d=>{dialogs++;expect(d.message()).toContain('Полный автономный QA');await d.accept();});
 await startFullQA(page);
 await navigate(page,'Отчёт');
 await expect(page.getByText('Цикл завершён без ручной корректировки результатов.',{exact:true})).toBeVisible({timeout:90000});
 await expect(page.getByText(/Исправление проверено.*Патч не применён/)).toBeVisible();
 expect(dialogs).toBe(1);
});
