// Explicit opt-in. Real HTTPS, own temporary projects, no LLM or patch application.
const {test}=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs/promises');const path=require('node:path');
test('live guest upload, history, gVisor Python/Playwright, account claim and privacy',{skip:!process.env.DEBUGYCH_WORKSPACE_LIVE_URL,timeout:180000},async()=>{
 const {chromium}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
 const url=process.env.DEBUGYCH_WORKSPACE_LIVE_URL,output=path.resolve(process.env.DEBUGYCH_WORKSPACE_EVIDENCE||'outputs/server10/workspaces');await fs.mkdir(output,{recursive:true});
 const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1365,height:1000}}),page=await context.newPage(),ids=[],results=[];let blocked=0;
 await context.route(/\/api\/.*(?:autonomous|analyze|propose-fix|apply-fix|companion\/ask)(?:\?|$)/,route=>{blocked++;return route.abort()});
 const headers={Origin:url},api=context.request;
 const json=async response=>{assert.ok(response.ok(),'Unexpected HTTP '+response.status());return response.json()};
 async function waitRun(id){for(let i=0;i<90;i++){const r=await json(await api.get(url+'/api/runs/'+id));if(!['queued','running','analyzing','generating'].includes(r.status))return r;await new Promise(r=>setTimeout(r,1000))}throw Error('Run did not finish')}
 try{
  await page.goto(url);await page.getByRole('button',{name:'Загрузить свой проект без регистрации'}).click();await page.getByText('Гостевая история этого браузера',{exact:true}).waitFor();
  await page.getByRole('button',{name:'Новый проект',exact:true}).click();await page.getByLabel('Название проекта').fill('Workspace QA Python '+Date.now());
  await page.getByLabel('Файлы нового проекта').setInputFiles([
   {name:'calc.py',mimeType:'text/plain',buffer:Buffer.from('def add(a,b): return a+b\n')},
   {name:'test_calc.py',mimeType:'text/plain',buffer:Buffer.from('from calc import add\ndef test_positive(): assert add(1,2)==3\ndef test_negative(): assert add(-1,1)==0\n')},
  ]);await page.getByRole('button',{name:'Создать проект',exact:true}).click();await page.getByRole('heading',{name:'Запуск собственных тестов'}).waitFor();
  const pythonProject=(await json(await api.get(url+'/api/projects'))).find(p=>p.name.startsWith('Workspace QA Python'));assert.ok(pythonProject);ids.push(pythonProject.id);
  await page.getByRole('button',{name:'Импортировать тесты без AI'}).click();await page.getByText('Тесты импортированы без AI. Можно запускать проверки.').waitFor();
  const pending=page.waitForResponse(r=>r.url().endsWith('/api/projects/'+pythonProject.id+'/runs')&&r.request().method()==='POST');await page.getByRole('button',{name:'Запустить тесты',exact:true}).click();const run=await json(await pending),completed=await waitRun(run.id);assert.equal(completed.status,'completed');assert.equal(completed.runtime,'runsc');assert.equal(completed.passed,2);assert.equal(completed.failed,0);results.push({profile:'pytest',id:run.id,passed:completed.passed,runtime:completed.runtime});
  await page.reload();await page.getByRole('heading',{name:'Запуск собственных тестов'}).waitFor();await page.screenshot({path:path.join(output,'guest-history.png'),fullPage:true});
  await page.goto(url+'/#/workspace/tests?project='+pythonProject.id);await page.getByText('Загруженный пользовательский тест · без AI-проверки ожиданий').waitFor();await page.screenshot({path:path.join(output,'guest-tests.png'),fullPage:true});
  const resumed=await browser.newContext({storageState:await context.storageState()});assert.equal((await json(await resumed.request.get(url+'/api/projects'))).length,1);await resumed.close();
  // Independent browser receives no project by knowing its ID.
  const other=await browser.newContext();const anonymous=await other.request.get(url+'/api/projects/'+pythonProject.id);assert.equal(anonymous.status(),404);await other.close();
  const js=await json(await api.post(url+'/api/projects',{headers,data:{name:'Workspace QA JS '+Date.now()}}));ids.push(js.id);
  for(const [name,code]of [['index.html','<h1>Counter</h1><button onclick="this.textContent=Number(this.textContent)+1">0</button>'],['counter.spec.ts',"import {test,expect} from '@playwright/test';test('counter',async({page})=>{await page.goto('/');await expect(page.locator('h1')).toHaveText('Counter');await page.getByRole('button').click();await expect(page.getByRole('button')).toHaveText('1')});"]])await json(await api.post(url+'/api/projects/'+js.id+'/files',{headers,multipart:{file:{name,mimeType:'text/plain',buffer:Buffer.from(code)}}}));
  await json(await api.post(url+'/api/projects/'+js.id+'/import-tests',{headers}));const jsRun=await json(await api.post(url+'/api/projects/'+js.id+'/runs',{headers}));const jsCompleted=await waitRun(jsRun.id);assert.equal(jsCompleted.status,'completed');assert.equal(jsCompleted.runtime,'runsc');assert.equal(jsCompleted.passed,1);assert.equal(jsCompleted.errors,0);results.push({profile:'playwright',id:jsRun.id,passed:jsCompleted.passed,runtime:jsCompleted.runtime});
  // Guest cookie survives closing its page and reopening in this browser context.
  await page.close();const reopened=await context.newPage();await reopened.goto(url);await reopened.getByText('Гостевая история этого браузера',{exact:true}).waitFor();assert.equal((await json(await api.get(url+'/api/projects'))).length,2);
  if(process.env.DEBUGYCH_ACCOUNT_CREDENTIALS){
   const data=JSON.parse(await fs.readFile(process.env.DEBUGYCH_ACCOUNT_CREDENTIALS,'utf8')),jury=data.accounts.find(a=>a.role==='jury');assert.ok(jury);
   await reopened.goto(url+'/auth/login');await reopened.getByLabel('Логин',{exact:true}).fill(jury.username);await reopened.getByLabel('Пароль',{exact:true}).fill(jury.password);await reopened.getByRole('button',{name:'Войти',exact:true}).click();await reopened.waitForURL('**/auth/account');
   const state=await json(await api.get(url+'/auth/session'));assert.equal(state.role,'jury');assert.equal(state.publicDemo,false);assert.equal(state.guest,false);const mine=await json(await api.get(url+'/api/projects'));assert.ok(ids.every(id=>mine.some(p=>p.id===id)));
   await reopened.goto(url+'/#/workspace/tests?project='+pythonProject.id);await reopened.getByText('Загруженный пользовательский тест · без AI-проверки ожиданий').waitFor();await reopened.screenshot({path:path.join(output,'jury-claimed-project.png'),fullPage:true});results.push({account:'jury',claimed:2});
  }
  assert.equal(blocked,0);await fs.writeFile(path.join(output,'results.json'),JSON.stringify({results,blocked_llm_or_patch_requests:blocked},null,2));console.log(JSON.stringify(results));
 }finally{
  for(const id of ids){const response=await api.delete(url+'/api/projects/'+id,{headers}).catch(()=>null);if(response&&!response.ok())console.log('Temporary project cleanup status',response.status())}
  await context.close();await browser.close();
 }
});
