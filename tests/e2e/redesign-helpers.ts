import {expect,type Page} from '../../apps/web/node_modules/@playwright/test';
export async function navigate(page:Page,name:string){
 if(['Обзор','Тесты','Ошибки','Отчёт'].includes(name)&&!await page.getByRole('navigation',{name:'Рабочая область проекта',exact:true}).isVisible()){
  const menu=page.getByRole('button',{name:'Меню',exact:true});if(await menu.isVisible()&&await menu.getAttribute('aria-expanded')==='false')await menu.click();
  await page.getByRole('button',{name:'Рабочая область',exact:true}).click();
 }
 if(['Обзор','Тесты','Ошибки','Отчёт'].includes(name)&&await page.getByRole('button',{name:'Меню',exact:true}).isVisible()&&await page.getByRole('button',{name:'Меню',exact:true}).getAttribute('aria-expanded')==='true')await page.getByRole('button',{name:'Закрыть меню',exact:true}).click();
 const button=page.getByRole('button',{name,exact:true});
 if(['Главная','Мои проекты','Рабочая область'].includes(name)){
  const menu=page.getByRole('button',{name:'Меню',exact:true});if(await menu.isVisible()&&await menu.getAttribute('aria-expanded')==='false')await menu.click();
 }
 await button.click();
}
export async function preparePlan(page:Page){
 await page.getByRole('button',{name:'3 Настройки',exact:true}).click();
 const details=page.getByText('Расширенные параметры и ограничения',{exact:true});
 if(!await page.getByRole('button',{name:'Только создать тестовый план'}).isVisible())await details.click();
 await page.getByRole('button',{name:'Только создать тестовый план'}).click();
}
export async function startFullQA(page:Page){await page.getByRole('button',{name:'4 Запуск',exact:true}).click();await page.getByRole('button',{name:'Начать проверку',exact:true}).click()}
export async function openDiff(page:Page){const control=page.getByText('Посмотреть предлагаемые изменения · diff',{exact:true});await expect(control).toBeVisible();if(!await page.getByLabel('Diff исправления',{exact:true}).isVisible())await control.click()}
export async function openAnalytics(page:Page){const control=page.getByText('Подробная аналитика и артефакты',{exact:true});if(!await page.getByRole('heading',{name:'Качество и требования'}).isVisible())await control.click()}
