import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Загруженный TypeScript → Playwright в gVisor → отчёт и скриншоты',async({page})=>{
 test.skip(process.env.COMPOSE_CONTRACT_TEST!=='1','Requires explicit contract-test provider');
 await page.goto('/');
 await page.getByRole('button',{name:'Новый проект'}).click();
 await page.getByLabel('Название проекта').fill('Uploaded TS · browser sandbox');
 await page.getByRole('button',{name:'Создать проект'}).click();
 await page.getByLabel('Загрузить файлы').setInputFiles([
  {name:'index.html',mimeType:'text/html',buffer:Buffer.from('<h1>Счётчик</h1><p id="value">0</p><button id="increment">Добавить</button><script type="module" src="/main.ts"></script>')},
  {name:'main.ts',mimeType:'text/plain',buffer:Buffer.from("let value: number = 0; document.querySelector('#increment')!.addEventListener('click',()=>{value-=1;document.querySelector('#value')!.textContent=String(value);console.log('Counter updated');});")},
  {name:'requirements.md',mimeType:'text/plain',buffer:Buffer.from('R1. Кнопка Добавить увеличивает счётчик на один. Начальное значение 0, заголовок Счётчик.')}
 ]);
 await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'AI-анализ',exact:true}).click();
 await page.getByRole('button',{name:'Открыть Test Studio'}).click();
 await expect(page.getByText('Браузерный счётчик · Playwright',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Запустить тесты'}).click();
 await expect(page.getByText('2 passed · 1 failed',{exact:false})).toBeVisible({timeout:45000});
 await expect(page.getByRole('heading',{name:'Фактические результаты Playwright'})).toBeVisible();
 await expect(page.getByText('Runtime: runsc',{exact:false})).toBeVisible();
 const images=page.getByRole('img',{name:/Скриншот screenshot-/});
 await expect(images).toHaveCount(3);
 for(const image of await images.all()) await expect(image).toHaveJSProperty('naturalWidth',960);
 const download=page.waitForEvent('download');
 await page.getByRole('link',{name:'playwright-report.json',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('playwright-report.json');
 await page.getByRole('button',{name:'Reports',exact:true}).click();
 await expect(page.getByText('Istanbul · собранный JavaScript',{exact:false})).toBeVisible();
 await expect(page.getByRole('link',{name:'coverage-istanbul.json',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Bug Lab',exact:false}).click();
 await expect(page.getByText('Reproduced · требует проверки').first()).toBeVisible();
 await expect(page.getByRole('button',{name:'Предложить патч'})).toBeDisabled();
});
