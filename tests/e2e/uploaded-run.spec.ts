import {navigate,preparePlan,openDiff} from './redesign-helpers';
import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Загрузка → Bug Proof → diff → gVisor regression → отдельное применение',async({page})=>{
 test.skip(process.env.COMPOSE_CONTRACT_TEST!=='1','Requires explicit compose.test.yml provider, not a real LLM key');
 await page.goto('/');
 await page.getByRole('button',{name:'Новый проект'}).click();
 await page.getByLabel('Название проекта').fill('Uploaded Python · browser contract');
 await page.getByRole('button',{name:'Создать проект'}).click();
 await page.getByLabel('Загрузить файлы').setInputFiles([
  {name:'calc.py',mimeType:'text/plain',buffer:Buffer.from('def add(a,b): return a-b\n')},
  {name:'requirements.md',mimeType:'text/markdown',buffer:Buffer.from('R1. Функция add возвращает сумму a и b.\n')}
 ]);
 await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());
 await preparePlan(page);
 await navigate(page,'Тесты');
 await expect(page.getByRole('heading',{name:'Сложение двух положительных чисел',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Запустить тесты'}).click();
 await expect(page.getByText('2 passed · 1 failed',{exact:false})).toBeVisible();
 await page.getByRole('tab',{name:'Результаты',exact:true}).click();
 await expect(page.getByText('Runtime: runsc',{exact:false})).toBeVisible();
 await navigate(page,'Ошибки');
 await expect(page.getByText('Воспроизведено, требует проверки').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'Предложить исправление'})).toBeDisabled();
 await page.getByLabel('Обоснование ожидания').fill('R1 требует математическую сумму: 2 + 3 = 5; assertion соответствует требованию.');
 await page.getByRole('checkbox').check();
 await page.getByRole('button',{name:'Подтвердить ожидание и воспроизвести'}).click();
 await expect(page.getByText('Подтверждено тестом',{exact:true}).first()).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Предложить исправление'}).click();
 await openDiff(page); await expect(page.getByText('+def add(a,b): return a+b',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Проверить исправление'}).click();
 await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeEnabled({timeout:30000});
 await expect(page.getByRole('heading',{name:'После исправления · полный регрессионный набор'})).toBeVisible();
 page.once('dialog',dialog=>dialog.dismiss());
 await page.getByRole('button',{name:'Подтвердить применение'}).click();
 await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeEnabled();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Подтвердить применение'}).click();
 await expect(page.getByRole('button',{name:'Патч применён'})).toBeDisabled();
 const downloaded=page.waitForEvent('download');
 await page.getByRole('link',{name:'Скачать исправленный проект'}).click();
 expect((await downloaded).suggestedFilename()).toBe('debugych-project.zip');
 await navigate(page,'Тесты');
 await page.getByRole('button',{name:'Запустить тесты'}).click();
 await expect(page.getByText('3 passed · 0 failed',{exact:false})).toBeVisible();
});
