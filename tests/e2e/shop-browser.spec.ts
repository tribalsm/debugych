import {test,expect} from '../../apps/web/node_modules/@playwright/test';
test.use({trace:'on'});

test('Доверенный Shop: доказательство ошибки точного баланса (ожидаемое падение)',async({page},testInfo)=>{
 await page.goto('/api/demo-web');
 await test.step('Ввести баланс и сумму 1000',async()=>{
  await page.getByLabel('Баланс').fill('1000');
  await page.getByLabel('Сумма платежа').fill('1000');
 });
 await test.step('Нажать «Оплатить»',()=>page.getByRole('button',{name:'Оплатить'}).click());
 await testInfo.attach('bug-proof.json',{body:JSON.stringify({requirement:'R1',expected:'Платёж принят',actual:await page.getByRole('status').textContent(),steps:['balance=1000','amount=1000','click Оплатить']}),contentType:'application/json'});
 await testInfo.attach('exact-balance.png',{body:await page.screenshot({fullPage:true}),contentType:'image/png'});
 test.fail(true,'Подготовленная buggy-версия нарушает R1. Этот assertion должен выявить ошибку.');
 await expect(page.getByRole('status')).toHaveText('Платёж принят',{timeout:800});
});

test('Доверенный Shop: исправленная версия принимает точный баланс',async({page})=>{
 await page.goto('/api/demo-web?fixed=true');
 await page.getByLabel('Баланс').fill('1000');
 await page.getByLabel('Сумма платежа').fill('1000');
 await page.getByRole('button',{name:'Оплатить'}).click();
 await expect(page.getByRole('status')).toHaveText('Платёж принят');
 await page.getByLabel('Сумма платежа').fill('1001');
 await page.getByRole('button',{name:'Оплатить'}).click();
 await expect(page.getByRole('status')).toHaveText('Платёж отклонён');
});
