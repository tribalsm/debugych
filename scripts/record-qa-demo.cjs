// Reproducible local evidence. No paid generation, remote writes or patch application.
const assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium,request}=require('../apps/web/node_modules/@playwright/test');
const BASE='http://127.0.0.1:8080',out=path.resolve(__dirname,'../outputs/server10/rag-ts/demo');
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms)); // Reading time in video, never simulated job progress.
async function main(){
 assert.equal(process.env.DEBUGYCH_DEMO_RECORD,'1','Explicit local recording opt-in required');
 await fs.mkdir(out,{recursive:true});const api=await request.newContext({baseURL:BASE});let pid,browser,context;
 const get=async url=>{const r=await api.get(url);assert.ok(r.ok(),'GET '+r.status());return r.json()};
 const post=async(url,data)=>{const r=await api.post(url,{data});assert.ok(r.ok(),'POST '+r.status());return r.json()};
 async function wait(id){for(let i=0;i<100;i++){const r=await get('/api/runs/'+id);if(!['queued','running','analyzing','generating'].includes(r.status)){assert.equal(r.status,'completed');return r}await pause(500)}throw Error('Prepared demo deadline')}
 try{
  const project=await post('/api/demo');assert.equal(project.demo,true);pid=project.id;
  await wait((await post(`/api/projects/${pid}/analyze`)).id);
  const original=await wait((await post(`/api/projects/${pid}/runs`)).id);assert.equal(original.failed,1);
  const bugs=await get('/api/bugs?project_id='+pid),bug=bugs[0];assert.ok(bug);
  const proposal=await post(`/api/bugs/${bug.id}/propose-fix`);assert.equal(proposal.origin,'prepared-demo');
  const verification=await wait((await post(`/api/bugs/${bug.id}/verify-fix`)).id);assert.equal(verification.passed,14);
  assert.ok((await get(`/api/projects/${pid}/fixes`)).every(f=>f.verified&&!f.applied));
  browser=await chromium.launch({headless:true});context=await browser.newContext({viewport:{width:1440,height:900},recordVideo:{dir:out,size:{width:1440,height:900}}});
  // Browser recording is read-only. Setup above uses only the explicit prepared demo.
  await context.route('**/api/**',route=>['GET','HEAD'].includes(route.request().method())?route.continue():route.abort());
  await context.addInitScript(()=>{localStorage.setItem('debugych-reduced-motion','true')});
  const page=await context.newPage(),video=page.video(),start=Date.now(),marks=[];
  async function mark(name){marks.push({name,milliseconds:Date.now()-start});await page.screenshot({path:path.join(out,name+'.png')})}
  await page.goto(BASE+'/#/workspace/tests?project='+pid);await page.getByRole('heading',{name:'Тестовый набор',exact:true}).waitFor();
  await mark('01-test-studio');await pause(2000);
  await page.getByRole('tab',{name:'Автотест',exact:true}).click();await page.getByLabel('Код · pytest',{exact:true}).scrollIntoViewIfNeeded();await mark('02-test-code');await pause(1800);
  await page.getByRole('button',{name:'Ошибки',exact:true}).click();await page.getByRole('button',{name:'Подтвердить применение',exact:true}).waitFor();
  await mark('03-bug-proof');await pause(2000);
  const trace=page.getByText('Посмотреть доказательство · traceback',{exact:true});await trace.click();await page.getByLabel('Traceback',{exact:true}).scrollIntoViewIfNeeded();await mark('04-traceback');await pause(1800);
  await page.getByText('Посмотреть предлагаемые изменения · diff',{exact:true}).click();await page.getByLabel('Diff исправления',{exact:true}).scrollIntoViewIfNeeded();await mark('05-fix-diff');await pause(2000);
  await page.locator('.comparison').scrollIntoViewIfNeeded();await mark('06-fix-verified');await pause(2800);
  await page.getByRole('button',{name:'Отчёт',exact:true}).click();await page.getByRole('heading',{name:'Успешность тестирования',exact:true}).waitFor();await mark('07-report');await pause(2300);
  await context.close();context=null;const filename=await video.path();
  await fs.writeFile(path.join(out,'recording.json'),JSON.stringify({video:filename,project_id:pid,prepared_demo:true,llm_requests:0,patch_applied:false,marks},null,2));
  assert.ok((await get(`/api/projects/${pid}/fixes`)).every(f=>!f.applied));
  console.log(JSON.stringify({video:filename,prepared_demo:true,llm_requests:0,patch_applied:false,frames:marks.length}));
 }finally{if(context)await context.close();if(browser)await browser.close();if(pid)await api.delete('/api/projects/'+pid);await api.dispose()}
}
main().catch(error=>{console.error(error.message);process.exitCode=1});
