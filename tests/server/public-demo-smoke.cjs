// No key, no login, no live generation. Requests to protected commands must fail.
const {chromium,expect}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
const assert=require('node:assert/strict'),fs=require('node:fs/promises');
(async()=>{
 const origin=process.env.DEBUGYCH_PUBLIC_URL||'https://debugych.89-22-232-119.sslip.io:9443',out=process.env.DEBUGYCH_PUBLIC_EVIDENCE||'outputs/server10/public-demo';await fs.mkdir(out,{recursive:true});
 const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),page=await context.newPage();const errors=[],writes=[];
 page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{if(!['GET','HEAD','OPTIONS'].includes(r.request().method())){writes.push(new URL(r.request().url()).pathname);return r.abort()}return r.continue()});
 const get=async path=>{const response=await context.request.get(origin+path);assert.equal(response.status(),200,path);assert.equal(response.headers()['x-debugych-public-demo'],'1');return response.json()};
 try{
  const projects=await get('/api/projects');assert.ok(projects.length>=3);const pid=projects.find(p=>p.name==='Server 1.0 offline control').id;assert.equal(pid,'78167145-424b-48a8-b3f9-6eefa284f3c3');
  const bug=(await get('/api/bugs?project_id='+pid))[0],fix=(await get('/api/projects/'+pid+'/fixes')).find(f=>f.id===bug.current_fix_id);assert.ok(fix.verified&&!fix.applied);
  const checked=[];
  async function visit(name,hash,check){await page.goto(origin+'/#/'+hash);await expect(page.getByText('Публичное демо · только просмотр',{exact:true})).toBeVisible();await expect(page.getByRole('status',{name:'Загружаем рабочее пространство'})).toHaveCount(0);await check();await page.screenshot({path:out+'/'+name+'.png',fullPage:false});checked.push(name)}
  await visit('dashboard','',async()=>expect(page.getByRole('button',{name:'Новый проект',exact:true})).toBeDisabled());
  await page.getByRole('button',{name:'Попробовать демо',exact:true}).click();await expect(page).toHaveURL(origin+'/#/workspace/overview?project='+pid);await expect(page.getByRole('heading',{name:'Результаты последнего запуска',exact:true})).toBeVisible();checked.push('dashboard-opens-control-project');
  await visit('projects','projects',async()=>expect(page.getByRole('button',{name:/Server 1\.0 offline control.*Загруженный проект/})).toBeVisible());
  await visit('tests',`workspace/tests?project=${pid}&run=${bug.run_id}`,async()=>{await expect(page.getByRole('heading',{name:'Фактические результаты pytest'})).toBeVisible();await expect(page.getByRole('button',{name:'Запустить тесты',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Редактировать сценарий'})).toBeDisabled()});
  const q=`workspace/bugs?project=${pid}&bug=${bug.id}&fix=${fix.id}`;
  await visit('proof',q+'&section=proof',async()=>{await expect(page.getByRole('heading',{name:bug.title,exact:true}).first()).toBeVisible();await expect(page.getByRole('button',{name:'Предложить исправление',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Проверить исправление',exact:true})).toBeDisabled();await expect(page.getByRole('button',{name:'Подтвердить применение',exact:true})).toBeDisabled()});
  await visit('diff',q+'&section=diff',async()=>expect(page.getByLabel('Diff исправления')).toContainText('+    return a + b'));
  await visit('verification',q+`&run=${fix.verification_id}&section=verification`,async()=>{await expect(page.getByRole('heading',{name:'После исправления · полный регрессионный набор'})).toBeVisible();await expect(page.getByRole('cell',{name:'2 успешно / 0 с отклонением',exact:true})).toBeVisible()});
  await visit('report',`workspace/report?project=${pid}&run=${fix.verification_id}`,async()=>expect(page.getByRole('heading',{name:'Отчёт о проверке',exact:true})).toBeVisible());
  await page.setViewportSize({width:390,height:844});await visit('mobile-proof',q+'&section=proof',async()=>expect(page.getByRole('heading',{name:bug.title,exact:true}).first()).toBeVisible());
  const blocked=[];
  for(const path of [`/api/projects/${pid}/autonomous`,`/api/projects/${pid}/files`,'/api/companion/ask',`/api/bugs/${bug.id}/verify-fix`,`/api/bugs/${bug.id}/apply-fix`]){const response=await context.request.post(origin+path,{data:{confirm:true},headers:{Origin:origin}});assert.equal(response.status(),403,path);blocked.push(path)}
  assert.equal((await context.request.get(origin+'/api/projects/00000000-1111-4111-8111-111111111111')).status(),404);
  assert.equal((await context.request.get(origin+'/docs')).status(),404);
  await page.goto(origin+'/auth/login');await expect(page.getByLabel('Логин',{exact:true})).toBeVisible();await page.getByRole('link',{name:'Зарегистрироваться',exact:true}).click();await expect(page.getByRole('heading',{name:'Создайте аккаунт',exact:true})).toBeVisible();checked.push('login-and-registration-available');
  assert.deepEqual(await context.cookies(),[]);assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  const result={classification:'PUBLIC_DEMO_NO_KEY_PASS',checked,projectCount:projects.length,serverDeniedCommands:blocked.length,otherProjectsHidden:true,ownerCookieCreated:false,browserErrors:errors,browserWrites:writes,patchApplied:false};await fs.writeFile(out+'/result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(e=>{console.error(String(e));process.exitCode=1});
