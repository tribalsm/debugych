// Read-only real backend browser smoke through the installed app's owned proxy.
// This is headless browser evidence, not native WebView/window lifecycle evidence.
const {chromium,expect}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
const fs=require('node:fs/promises'),assert=require('node:assert/strict');
let sensitive='';
// ZIP headers include export timestamps. Compare file names and actual contents.
const archiveManifest=buffer=>JSON.parse(require('node:child_process').execFileSync('python',['-c',
 'import sys,io,zipfile,json,hashlib; z=zipfile.ZipFile(io.BytesIO(sys.stdin.buffer.read())); print(json.dumps(sorted((i.filename,hashlib.sha256(z.read(i)).hexdigest()) for i in z.infolist() if not i.is_dir())))'],{input:buffer,encoding:'utf8'}));
(async()=>{
 const base=process.env.DEBUGYCH_INSTALLED_ORIGIN;
 const publicWeb=base==='https://debugych.89-22-232-119.nip.io:9443';
 const verifyAgain=publicWeb&&process.env.DEBUGYCH_VERIFY_EXISTING_FIX==='1';let allowedVerification='',uiVerification=null;
 assert.ok(publicWeb||/^http:\/\/127\.0\.0\.1:\d+$/.test(base||''));
 const pid='78167145-424b-48a8-b3f9-6eefa284f3c3';
 const out=process.env.DEBUGYCH_SMOKE_OUTPUT||'outputs/server10/installed-headless';await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
 const page=await context.newPage();const failures=[],blockedWrites=[];
 page.on('pageerror',e=>failures.push(e.message));
 page.on('response',r=>{if(r.url().startsWith(base+'/api/')&&r.status()>=500)failures.push('HTTP '+r.status()+' '+new URL(r.url()).pathname)});
 await page.route('**/*',route=>{
  const url=new URL(route.request().url());
  const allowedWrite=publicWeb&&url.origin===base&&(url.pathname==='/auth/login'||(verifyAgain&&url.pathname===allowedVerification&&route.request().method()==='POST'));
  if(!['GET','HEAD','OPTIONS'].includes(route.request().method())&&!allowedWrite){blockedWrites.push(url.pathname);return route.abort()}
  return route.continue();
 });
 const get=async path=>{const r=await context.request.get(base+path);assert.equal(r.status(),200,path);return r.json()};
 try{
  if(publicWeb){
   let raw='';for await(const chunk of process.stdin)raw+=chunk;sensitive=JSON.parse(raw).token;raw='';assert.match(sensitive,/^[-_A-Za-z0-9]{43,256}$/);
   const anonymous=await context.request.get(base+'/api/projects');if(anonymous.status()===200){const visible=await anonymous.json();assert.equal(visible.length,1);assert.equal(visible[0].id,pid)}else assert.equal(anonymous.status(),401);
   await page.goto(base+'/auth/login?owner=1');await expect(page.getByLabel('Ключ доступа')).toBeVisible();await page.screenshot({path:out+'/login.png'});
   const rejected=await context.request.post(base+'/auth/login',{headers:{Origin:base},form:{token:'invalid'},maxRedirects:0});assert.equal(rejected.status(),401);
   await page.getByLabel('Ключ доступа').fill(sensitive);await page.getByRole('button',{name:'Войти в Дебагыч'}).click();await expect(page).toHaveURL(base+'/');
   const cookies=await context.cookies(base),session=cookies.find(c=>c.name==='__Host-debugych');assert.ok(session?.secure&&session.httpOnly&&session.sameSite==='Strict');assert.notEqual(session.value,sensitive);
   assert.equal(await page.evaluate(()=>document.cookie.includes('__Host-debugych')),false);
   assert.ok(!(await page.evaluate(()=>JSON.stringify([Object.entries(localStorage),Object.entries(sessionStorage)]))).includes(sensitive));
  }
  const health=await get('/api/health');assert.equal(health.sandbox_available,true);
  const bugs=await get('/api/bugs?project_id='+pid),bug=bugs.find(b=>b.status==='fix_verified');assert.ok(bug);
  const fix=(await get(`/api/projects/${pid}/fixes`)).find(f=>f.id===bug.current_fix_id);assert.ok(fix.verified&&!fix.applied);
  const before=await get(`/api/projects/${pid}/ai-statistics`);
  const archive=await context.request.get(base+`/api/projects/${pid}/source-archive`);assert.equal(archive.status(),200);
  const sourceBefore=archiveManifest(await archive.body());
  const checked=[];
  async function visit(name,route,check){await page.goto(base+'/#/'+route);await check();await page.screenshot({path:out+'/'+name+'.png',fullPage:true});checked.push(name)}
  await visit('dashboard','',async()=>expect(page.getByRole('heading').first()).toBeVisible());
  await visit('projects','projects',async()=>expect(page.getByRole('button',{name:/Server 1\.0 offline control.*Загруженный проект/})).toBeVisible());
  await visit('tests',`workspace/tests?project=${pid}&run=${bug.run_id}`,async()=>expect(page.getByRole('heading',{name:'Фактические результаты pytest'})).toBeVisible());
  const q=`workspace/bugs?project=${pid}&bug=${bug.id}&fix=${fix.id}`;
  await visit('proof',q+'&section=proof',async()=>{await expect(page.getByRole('heading',{name:bug.title,exact:true}).first()).toBeVisible();await expect(page.getByText('Повторить тест в том же образе gVisor')).toBeVisible()});
  if(verifyAgain){
   allowedVerification='/api/bugs/'+bug.id+'/verify-fix';
   const pending=page.waitForResponse(r=>r.url()===base+allowedVerification&&r.request().method()==='POST');
   await page.getByRole('button',{name:'Проверить исправление',exact:true}).click();const response=await pending;assert.equal(response.status(),202);const job=await response.json();
   const deadline=Date.now()+120000;let run;
   do{run=await get('/api/runs/'+job.id);if(['completed','failed','cancelled'].includes(run.status))break;if(Date.now()>deadline)throw Error('gVisor verification deadline');await new Promise(r=>setTimeout(r,500))}while(true);
   assert.ok(run.status==='completed'&&run.verified&&run.runtime==='runsc'&&run.passed===2&&run.failed===0&&run.assessment.tests_unchanged);
   fix.verification_id=job.id;uiVerification={id:job.id,runtime:run.runtime,passed:run.passed,failed:run.failed,testsUnchanged:run.assessment.tests_unchanged};allowedVerification='';checked.push('web-button-starts-real-gvisor-verification');
  }
  await visit('diff',q+'&section=diff',async()=>{await expect(page.getByLabel('Diff исправления')).toBeVisible();await expect(page.getByLabel('Diff исправления')).toContainText('+    return a + b')});
  await visit('verification',q+`&run=${fix.verification_id}&section=verification`,async()=>{await expect(page.getByRole('heading',{name:'После исправления · полный регрессионный набор'})).toBeVisible();await expect(page.getByRole('cell',{name:'2 успешно / 0 с отклонением',exact:true})).toBeVisible()});
  await visit('report',`workspace/report?project=${pid}&run=${fix.verification_id}`,async()=>expect(page.getByRole('heading').first()).toBeVisible());
  await page.setViewportSize({width:390,height:844});
  await visit('mobile-proof',q+'&section=proof',async()=>expect(page.getByRole('heading',{name:bug.title,exact:true}).first()).toBeVisible());
  await page.goto(base+`/#/workspace/bugs?project=${pid}&bug=bad&section=proof`);await expect(page.getByRole('alert')).toContainText('Некорректная ссылка');checked.push('invalid-link-fails-closed');
  const after=await get(`/api/projects/${pid}/ai-statistics`);assert.equal(after.attempts,before.attempts);assert.equal(after.calls.length,before.calls.length);
  assert.equal((await get(`/api/projects/${pid}/fixes`)).find(f=>f.id===fix.id).applied,false);
  const archiveAfter=await context.request.get(base+`/api/projects/${pid}/source-archive`);assert.equal(archiveAfter.status(),200);assert.deepEqual(archiveManifest(await archiveAfter.body()),sourceBefore);
  assert.deepEqual(failures,[]);assert.deepEqual(blockedWrites,[]);
  if(publicWeb){await page.goto(base+'/auth/account');await expect(page.getByRole('button',{name:'Выйти из сеанса'})).toBeVisible();const logout=await context.request.post(base+'/auth/logout',{headers:{Origin:base},maxRedirects:0});assert.equal(logout.status(),303);assert.equal((await context.request.get(base+'/auth/account',{maxRedirects:0})).status(),303);checked.push('login-HttpOnly-session-and-logout')}
  const report={classification:publicWeb?'PUBLIC_HTTPS_WEB_UI_PASS':'INSTALLED_PROXY_HEADLESS_UI_PASS',nativeWindowInteraction:'NOT TESTED',checked,uiVerification,newLLMCalls:after.calls.length-before.calls.length,patchApplied:false,sourceUnchanged:true,browserErrors:failures,blockedWrites};
  await fs.writeFile(out+'/result.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{console.error(sensitive?String(e).replaceAll(sensitive,'[REDACTED]'):String(e));process.exitCode=1});
