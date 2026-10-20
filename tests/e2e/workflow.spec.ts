import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Демо: требования → тест → доказательство → патч → проверка → применение',async({page})=>{
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Всё под контролем.'})).toBeVisible();
 await page.getByRole('button',{name:'Попробовать на демопроекте'}).click();
 await expect(page.getByText('DEMO · подготовленные тесты')).toBeVisible();
 await page.getByRole('button',{name:'Загрузить демоплан'}).click();
 await page.getByRole('button',{name:'Открыть Test Studio'}).click();
 await expect(page.getByRole('heading',{name:'Границы оплаты, скидки и количества',exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Запустить тесты'}).click();
 await expect(page.getByText('13 passed · 1 failed', {exact:false})).toBeVisible();
 await page.getByRole('button',{name:'Bug Lab'}).click();
 await expect(page.getByText('False — платёж отклонён')).toBeVisible();
 await page.getByRole('button',{name:'Предложить патч'}).click();
 await expect(page.getByText('+    return balance >= amount',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Проверить в копии'}).click();
 await expect(page.getByRole('button',{name:'Подтвердить применение'})).toBeEnabled();
 page.once('dialog',dialog=>dialog.accept());
 await page.getByRole('button',{name:'Подтвердить применение'}).click();
 await expect(page.getByRole('button',{name:'Патч применён'})).toBeDisabled();
 await page.getByRole('button',{name:'Reports'}).click();
 await expect(page.getByText('14', {exact:true}).first()).toBeVisible();
 const download=page.waitForEvent('download');
 await page.getByRole('button',{name:'.feature',exact:true}).click();
 expect((await download).suggestedFilename()).toBe('debugych.feature');
});

test('Создание проекта, сохранение файла и честное ограничение исполнения',async({page})=>{
 await page.goto('/');
 await page.getByRole('button',{name:'Новый проект'}).click();
 await page.getByLabel('Название проекта').fill('Browser upload test');
 await page.getByRole('button',{name:'Создать проект'}).click();
 await page.getByLabel('Загрузить файлы').setInputFiles({name:'requirements.md',mimeType:'text/markdown',buffer:Buffer.from('# Требования\nR1. Проверить баланс.')});
 await expect(page.getByText('requirements.md',{exact:true})).toBeVisible();
 await page.getByRole('button',{name:'Test Studio',exact:true}).click();
 await expect(page.getByRole('button',{name:'Запустить тесты'})).toBeDisabled();
});

test('Адаптивный Dashboard на мобильном экране',async({page})=>{
 await page.setViewportSize({width:390,height:844});
 await page.goto('/');
 await expect(page.getByRole('heading',{name:'Всё под контролем.'})).toBeVisible();
 await expect(page.getByRole('button',{name:'Новый проект'})).toBeVisible();
 expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBe(true);
 await page.getByRole('button',{name:'Меню',exact:true}).click();
 await page.getByRole('button',{name:'Projects'}).click();
 await expect(page.getByRole('heading',{name:'Ваши проекты'})).toBeVisible();
});

test('Устаревший выбранный проект восстанавливается после смены backend',async({page})=>{
 await page.goto('/');
 const invalid='00000000-0000-4000-8000-000000000001';
 await page.evaluate(id=>localStorage.setItem('debugych-project',id),invalid);
 await page.reload();
 await expect(page.getByLabel('Текущий проект')).not.toHaveValue(invalid);
 await expect(page.getByRole('alert')).toHaveCount(0);
});
