import {test,expect} from '../../apps/web/node_modules/@playwright/test';
const pid=process.env.V31_PROJECT_ID;
test.skip(!pid,'Explicit isolated existing live control required; never creates a paid job');
test('exact proof, diff, test run and verification links use real saved records',async({page,request})=>{
 const api=process.env.V31_API||'http://127.0.0.1:8000';
 const bugs=await(await request.get(api+'/api/bugs?project_id='+pid)).json();const bug=bugs.find((b:{status:string})=>b.status==='fix_verified');expect(bug).toBeTruthy();
 const fixes=await(await request.get(`${api}/api/projects/${pid}/fixes`)).json();const fix=fixes.find((f:{bug_id:string;verified:boolean})=>f.bug_id===bug.id&&f.verified);expect(fix.applied).toBe(false);
 await page.goto(`/#/workspace/bugs?project=${pid}&bug=${bug.id}&fix=${fix.id}&section=diff`);
 await expect(page.getByLabel('Diff исправления')).toBeVisible();await expect(page.getByLabel('Diff исправления')).toContainText('+    return balance >= amount');
 await page.goto(`/#/workspace/bugs?project=${pid}&bug=${bug.id}&run=${bug.run_id}&section=proof`);
 await expect(page.getByRole('heading',{name:bug.title,exact:true}).first()).toBeVisible();await expect(page.getByRole('region',{name:'Traceback'})).toHaveCount(0);await expect(page.getByText('Повторить тест в том же образе gVisor')).toBeVisible();
 await page.goto(`/#/workspace/tests?project=${pid}&run=${bug.run_id}`);await expect(page.getByRole('heading',{name:'Фактические результаты pytest'})).toBeVisible();await expect(page.getByText('7 passed · 1 failed', {exact:false}).first()).toBeVisible();
 await page.goto(`/#/workspace/bugs?project=${pid}&bug=${bug.id}&fix=${fix.id}&run=${fix.verification_id}&section=verification`);await expect(page.getByRole('heading',{name:'После исправления · полный регрессионный набор'})).toBeVisible();await expect(page.getByText('8 passed · 0 failed', {exact:false}).first()).toBeVisible();
 expect((await(await request.get(`${api}/api/projects/${pid}/fixes`)).json()).find((f:{id:string})=>f.id===fix.id).applied).toBe(false);
});
test('foreign bug and mismatched verification fail closed without substituting latest result',async({page})=>{
 await page.goto(`/#/workspace/bugs?project=${pid}&bug=00000000-1111-4111-8111-111111111111&section=proof`);await expect(page.getByRole('alert')).toContainText('не найден');await expect(page.getByRole('button',{name:'Подтвердить применение',exact:true})).toHaveCount(0);
 await page.goto(`/#/workspace/bugs?project=${pid}&bug=bad&section=proof`);await expect(page.getByRole('alert')).toContainText('Некорректная ссылка');
});
