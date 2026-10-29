// Explicit new-domain check. Own temporary projects only, no LLM or patch application.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
test('new HTTPS domain supports account login, uploads, gVisor and exact-origin CSRF',{skip:!process.env.DEBUGYCH_DOMAIN_ACCOUNT_CHECK,timeout:180000},async()=>{
 const url='https://debugych.89-22-232-119.sslip.io:9443';
 const {chromium}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
 const data=JSON.parse(await fs.readFile(process.env.DEBUGYCH_ACCOUNT_CREDENTIALS,'utf8')),user=data.accounts.find(a=>a.role==='jury');assert.ok(user);
 const out=path.resolve('outputs/server10/free-domain');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true}),context=await browser.newContext(),page=await context.newPage(),api=context.request,headers={Origin:url},ids=[],results=[];let blocked=0;
 await context.route(/\/api\/.*(?:autonomous|analyze|propose-fix|apply-fix|companion\/ask)(?:\?|$)/,route=>{blocked++;return route.abort()});
 const json=async r=>{assert.ok(r.ok(),'HTTP '+r.status());return r.json()};
 async function wait(id){for(let i=0;i<90;i++){const r=await json(await api.get(url+'/api/runs/'+id));if(!['queued','running','analyzing','generating'].includes(r.status))return r;await new Promise(r=>setTimeout(r,1000))}throw Error('Execution deadline')}
 try{
  await page.goto(url+'/auth/login');await page.getByLabel('Логин',{exact:true}).fill(user.username);await page.getByLabel('Пароль',{exact:true}).fill(user.password);await page.getByRole('button',{name:'Войти',exact:true}).click();await page.waitForURL('**/auth/account');
  const state=await json(await api.get(url+'/auth/session'));assert.equal(state.role,'jury');assert.equal(state.publicDemo,false);
  const fixtures=[['pytest',2,{'calc.py':'def add(a,b): return a+b','test_calc.py':'from calc import add\ndef test_add(): assert add(1,2)==3\ndef test_zero(): assert add(-1,1)==0'}],['playwright',1,{'index.html':'<h1>Counter</h1><button>0</button><script type="module" src="/app.js"></script>','app.js':"const b=document.querySelector('button');b.addEventListener('click',()=>{b.textContent=String(Number(b.textContent)+1)})",'counter.spec.ts':"import {test,expect} from '@playwright/test';test('counter',async({page})=>{await page.goto('/');await page.getByRole('button').click();await expect(page.getByRole('button')).toHaveText('1')});"}]];
  for(const [profile,count,files]of fixtures){
   const p=await json(await api.post(url+'/api/projects',{headers,data:{name:'New domain control '+profile+' '+Date.now()}}));ids.push(p.id);
   for(const [name,code]of Object.entries(files))await json(await api.post(url+'/api/projects/'+p.id+'/files',{headers,multipart:{file:{name,mimeType:'text/plain',buffer:Buffer.from(code)}}}));
   await json(await api.post(url+'/api/projects/'+p.id+'/import-tests',{headers}));
   assert.equal((await api.post(url+'/api/projects/'+p.id+'/runs',{headers:{Origin:'https://debugych.89-22-232-119.nip.io:9443'}})).status(),403);
   const job=await json(await api.post(url+'/api/projects/'+p.id+'/runs',{headers})),r=await wait(job.id);
   assert.equal(r.status,'completed');assert.equal(r.runtime,'runsc');assert.equal(r.passed,count);assert.equal(r.failed,0);assert.equal(r.errors,0);
   assert.equal((await json(await api.get(url+'/api/projects/'+p.id+'/ai-statistics'))).attempts,0);
   await page.goto(url+'/#/workspace/tests?project='+p.id);await page.getByText('Загруженный пользовательский тест · без AI-проверки ожиданий').waitFor();await page.screenshot({path:path.join(out,profile+'-account.png'),fullPage:true});
   results.push({profile,passed:r.passed,runtime:r.runtime,id:job.id});
  }
  assert.equal(blocked,0);await fs.writeFile(path.join(out,'account-results.json'),JSON.stringify({results,llm_requests:0,patch_applications:0},null,2));console.log(JSON.stringify(results));
 }finally{
  for(const id of ids){const r=await api.delete(url+'/api/projects/'+id,{headers}).catch(()=>null);if(r&&!r.ok())console.log('Cleanup HTTP',r.status())}
  await api.post(url+'/auth/logout',{headers,form:{}}).catch(()=>{});await context.close();await browser.close();
 }
});
