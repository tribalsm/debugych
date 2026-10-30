// Explicit opt-in: own temporary project, local embedding and gVisor, no paid AI.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium}=require('../../apps/web/node_modules/@playwright/test');
const BASE='https://debugych.89-22-232-119.sslip.io:9443';
async function main(){
 assert.equal(process.env.DEBUGYCH_RETRIEVAL_LIVE_CHECK,'1');
 const credentials=JSON.parse(await fs.readFile(process.env.DEBUGYCH_ACCOUNT_CREDENTIALS,'utf8')),user=credentials.accounts.find(a=>a.role==='jury');assert.ok(user);
 const out=path.resolve('outputs/server10/rag-ts/live');await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:900}}),api=context.request,headers={Origin:BASE};let pid,blocked=0;
 const json=async response=>{assert.ok(response.ok(),'HTTP '+response.status());return response.json()};
 await context.route(/\/api\/.*(?:autonomous|analyze|propose-fix|apply-fix|companion\/ask)(?:\?|$)/,route=>{blocked++;return route.abort()});
 try{
  const login=await api.post(BASE+'/auth/sign-in',{headers,form:{username:user.username,password:user.password},maxRedirects:0});assert.equal(login.status(),303);
  pid=(await json(await api.post(BASE+'/api/projects',{headers,data:{name:'Контроль TS: локальный поиск и исходные строки'}}))).id;
  const files={
   'index.html':'<button>Check</button><output></output><script type="module" src="/main.ts"></script>',
   'rules.ts':"type Amount = number;\nexport function describe(n: Amount): string {\n  if (n === 0) {\n    return 'Empty';\n  }\n  return 'Active';\n}\n",
   'main.ts':"import {describe} from './rules';\ndocument.querySelector('button')!.onclick=()=>{document.querySelector('output')!.textContent=describe(0)};",
   'requirements.md':'R1. Checking the zero value displays Empty. A nonzero value displays Active.\nAPI_KEY="fixture-sentinel-never-a-real-key"',
   'control.spec.ts':"import {test,expect} from '@playwright/test';test('zero state',async({page})=>{await page.goto('/');await page.getByRole('button').click();await expect(page.locator('output')).toHaveText('Empty')});",
  };
  for(const [name,code]of Object.entries(files))await json(await api.post(BASE+`/api/projects/${pid}/files`,{headers,multipart:{file:{name,mimeType:'text/plain',buffer:Buffer.from(code)}}}));
  await json(await api.post(BASE+`/api/projects/${pid}/import-tests`,{headers}));
  const job=await json(await api.post(BASE+`/api/projects/${pid}/runs`,{headers}));let run;
  for(let i=0;i<90;i++){run=await json(await api.get(BASE+'/api/runs/'+job.id));if(!['queued','running'].includes(run.status))break;await new Promise(r=>setTimeout(r,1000))}
  assert.equal(run.status,'completed');assert.equal(run.runtime,'runsc');assert.equal(run.passed,1);assert.equal(run.coverage_kind,'istanbul-original-source');
  assert.deepEqual(run.coverage.files['rules.ts'].executed_lines,[3,4]);assert.deepEqual(run.coverage.files['rules.ts'].missing_lines,[6]);
  const page=await context.newPage();await page.goto(BASE+'/#/workspace/tests?project='+pid);
  await page.getByText('Поиск по коду и требованиям',{exact:true}).click();await page.getByLabel('Что найти в проекте?').fill('Обработка нулевого значения и описание состояния');
  const response=page.waitForResponse(r=>r.url().endsWith('/context-search')&&r.request().method()==='POST');await page.getByRole('button',{name:'Найти',exact:true}).click();const result=await json(await response);
  assert.equal(result.mode,'pgvector-semantic');assert.ok(result.matches.length);assert.ok(!JSON.stringify(result).includes('fixture-sentinel-never-a-real-key'));
  await page.getByText('Семантический поиск с локальной моделью.',{exact:false}).waitFor();await page.locator('.context-search').scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'01-semantic-search.png')});
  await page.getByRole('button',{name:'Отчёт',exact:true}).click();await page.getByRole('heading',{name:'Покрытие кода',exact:true}).waitFor();
  await page.getByText('rules.ts',{exact:true}).click();await page.getByRole('heading',{name:'Покрытие кода',exact:true}).scrollIntoViewIfNeeded();await page.screenshot({path:path.join(out,'02-original-typescript.png')});
  const xml=await api.get(BASE+`/api/exports?project_id=${pid}&format=junit&run_id=${run.id}`);assert.ok(xml.ok());await fs.writeFile(path.join(out,'junit.xml'),await xml.body());
  assert.equal((await json(await api.get(BASE+`/api/projects/${pid}/ai-statistics`))).attempts,0);assert.equal(blocked,0);
  const anonymous=await browser.newContext();try{const denied=await anonymous.request.post(BASE+`/api/projects/${pid}/context-search`,{headers,data:{query:'private project'}});assert.ok([401,403,404].includes(denied.status()))}finally{await anonymous.close()}
  const evidence={run_id:run.id,runtime:run.runtime,passed:run.passed,coverage_kind:run.coverage_kind,coverage:run.coverage,retrieval_mode:result.mode,encoder:result.encoder,llm_requests:0,patch_applications:0,anonymous_denied:true};
  await fs.writeFile(path.join(out,'results.json'),JSON.stringify(evidence,null,2));console.log(JSON.stringify(evidence));
 }finally{if(pid){const r=await api.delete(BASE+'/api/projects/'+pid,{headers});assert.ok(r.ok(),'Temporary project cleanup failed')}await context.close();await browser.close()}
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
