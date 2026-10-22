import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {navigate} from './redesign-helpers';

test('Большие мониторы: шесть экранов на 1920 и 2560 без переполнения страницы',async({page,request})=>{
 // This scenario must also work alone and against a newly created database.
 const response=await request.post('/api/demo');expect(response.ok()).toBeTruthy();const demo=await response.json();expect(demo.demo).toBe(true);
 for(const width of [1920,2560]){
  await page.setViewportSize({width,height:1080});await page.goto('/#/workspace/overview?project='+demo.id);await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toHaveCount(0);
  for(const name of ['Главная','Мои проекты','Обзор','Тесты','Ошибки','Отчёт']){
   await navigate(page,name);await expect(page.locator('main h1')).toBeVisible();
   const size=await page.evaluate(()=>({viewport:innerWidth,scroll:document.documentElement.scrollWidth}));expect(size.scroll,`${name}, ${width}px`).toBeLessThanOrEqual(size.viewport);
  }
 }
});
