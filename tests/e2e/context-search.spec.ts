import {test,expect} from '../../apps/web/node_modules/@playwright/test';

test('Поиск в своём проекте работает без AI и очищает результаты при смене проекта',async({page,request})=>{
 const p=await(await request.post('/api/projects',{data:{name:'Context search UI'}})).json();
 await request.post(`/api/projects/${p.id}/files`,{multipart:{file:{name:'requirements.md',mimeType:'text/plain',buffer:Buffer.from('Payment succeeds at exact balance.')}}});
 let ai=0;await page.route(/\/api\/projects\/[^/]+\/(analyze|autonomous|ai-context)$/,route=>{ai++;return route.abort()});
 await page.goto('/#/workspace/tests?project='+p.id);
 await page.getByText('Поиск по коду и требованиям',{exact:true}).click();
 await page.getByLabel('Что найти в проекте?').fill('payment balance');await page.getByRole('button',{name:'Найти',exact:true}).click();
 await expect(page.locator('.context-search')).toContainText('requirements.md');
 await page.locator('.context-search summary').filter({hasText:'requirements.md'}).click();await expect(page.locator('.context-search')).toContainText('Payment succeeds at exact balance.');
 const other=await(await request.post('/api/projects',{data:{name:'Empty other context'}})).json();
 await page.goto('/#/workspace/tests?project='+other.id);await expect(page.getByLabel('Что найти в проекте?')).toHaveValue('');
 await expect(page.locator('.context-search')).not.toContainText('Payment succeeds at exact balance.');expect(ai).toBe(0);
});
