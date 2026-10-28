// Real HTTPS UI and API through the shipping proxy. Native IPC is a contract
// double in a headless browser: this does not claim Windows window testing.
const {chromium,expect}=require(require.resolve('@playwright/test',{paths:[require('node:path').resolve('apps/web')]}));
const {spawn}=require('node:child_process'),fs=require('node:fs/promises'),path=require('node:path'),assert=require('node:assert/strict'),net=require('node:net');
const {createHash}=require('node:crypto');
const server='https://debugych.89-22-232-119.nip.io:9443';
const project='78167145-424b-48a8-b3f9-6eefa284f3c3';
const digest=b=>createHash('sha256').update(b).digest('hex');
const nativeFetch=global.fetch;global.fetch=(url,options={})=>nativeFetch(url,{signal:AbortSignal.timeout(15000),...options});
let secrets=[];
async function run(){
 let input='';for await(const chunk of process.stdin)input+=chunk;
 const account=JSON.parse(input);input='';secrets.push(account.password);
 const login=await fetch(server+'/auth/sign-in',{method:'POST',redirect:'manual',headers:{Origin:server,'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({username:account.username,password:account.password})});
 assert.equal(login.status,303,'HTTPS account login');
 console.log('HTTPS login passed');
 const sid=login.headers.getSetCookie().join(';').match(/__Host-debugych=([a-f0-9]{64})/)?.[1];assert.ok(sid);secrets.push(sid);account.password='';
 const listener=net.createServer();await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
 const base='http://127.0.0.1:'+port,out='outputs/server10/thin-live-'+account.role;await fs.mkdir(out,{recursive:true});
 const child=spawn(process.execPath,['scripts/serve-web.mjs'],{env:{...process.env,DEBUGYCH_WEB_PORT:String(port),DEBUGYCH_API_URL:server,DEBUGYCH_ALLOW_REMOTE_API:'1',DEBUGYCH_UI_SOURCE:'remote',DEBUGYCH_DESKTOP_EMBED:'1',DEBUGYCH_REMOTE_AUTH_STDIN:'1'},stdio:['pipe','pipe','pipe'],windowsHide:true});
 child.stdin.end(JSON.stringify({session:sid})+'\n');
 await new Promise((resolve,reject)=>{const timeout=setTimeout(()=>reject(Error('Proxy startup timeout')),10000);child.stdout.once('data',()=>{clearTimeout(timeout);resolve()});child.once('exit',code=>{clearTimeout(timeout);reject(Error('Proxy exited '+code))});child.stderr.on('data',()=>{});});console.log('Shipping proxy ready');
 const browser=await chromium.launch({headless:true});
 try{
  const remote=await fetch(server),local=await fetch(base),html=await local.text();assert.equal(digest(html),digest(await remote.text()));assert.equal(local.headers.get('cache-control'),'no-store');assert.equal(local.headers.get('set-cookie'),null);
  console.log('Server HTML byte identity passed');
  const asset=html.match(/src="(\/assets\/[^\"]+\.js)"/)?.[1];assert.ok(asset);
  assert.equal(digest(Buffer.from(await(await fetch(base+asset)).arrayBuffer())),digest(Buffer.from(await(await fetch(server+asset)).arrayBuffer())));
  const get=async p=>{const r=await fetch(base+p);assert.equal(r.status,200,p);return r.json()};
  const before=await get(`/api/projects/${project}/ai-statistics`),bugs=await get('/api/bugs?project_id='+project),bug=bugs.find(b=>b.status==='fix_verified');assert.ok(bug);
  const fix=(await get(`/api/projects/${project}/fixes`)).find(f=>f.id===bug.current_fix_id);assert.ok(fix.verified&&!fix.applied);
  console.log('Real QA evidence retrieved');
  const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'}),page=await context.newPage(),errors=[],writes=[];
  page.on('pageerror',e=>errors.push(e.message));
  await page.route('**/*',async route=>{
   const url=new URL(route.request().url());
   if(url.origin==='http://tauri.localhost'){
    const file=url.pathname==='/'?'index.html':url.pathname.slice(1);assert.ok(['index.html','shell.js','shell.css'].includes(file));
    return route.fulfill({body:await fs.readFile(path.resolve('apps/desktop/shell',file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'});
   }
   if(!['GET','HEAD','OPTIONS'].includes(route.request().method())){writes.push(url.pathname);return route.abort()}
   assert.equal(url.origin,base,'UI remains on the credential-free loopback origin');return route.continue();
  });
  await page.addInitScript(({base,server,project,role})=>{
   if(location.hostname!=='tauri.localhost')return;
   window.calls=[];window.listeners={};window.ctx={backendUrl:server,frontendUrl:base,projectId:project,revision:1,petVisible:true};
   window.__TAURI__={event:{listen:async(n,f)=>{listeners[n]=f}},core:{invoke:async(n,args)=>{
    calls.push({name:n,args});
    if(n==='get_desktop_context')return {...ctx};if(n==='start_application')return base+'/';if(n==='startup_status')return '';
    if(n==='get_config')return {mode:'remote',api_url:server,backend_root:'',route_ip:'',config_directory:'Headless contract'};
    if(n==='account_info')return {saved:true,username:'HTTPS '+role,role};
    if(n==='set_selected_project'){if(args.revision!==ctx.revision)throw Error('stale revision');ctx.projectId=args.projectId;ctx.revision++;return {...ctx}}
    if(n==='set_pet_visible'){ctx.petVisible=args.visible;ctx.revision++;return {...ctx}}
    throw Error('Unexpected native command '+n);
   }}};
  },{base,server,project,role:account.role});
  await page.goto('http://tauri.localhost/');await expect(page.locator('#workspace')).toBeVisible();
  const frame=page.frames().find(f=>f.url().startsWith(base));assert.ok(frame);await expect(frame.getByRole('heading',{name:'Server 1.0 offline control',exact:true}).first()).toBeVisible({timeout:30000});
  assert.equal(await frame.evaluate(()=>typeof window.__TAURI__),'undefined');
  await frame.getByRole('button',{name:'Аккаунт',exact:true}).click();await expect(page.locator('#settings')).toBeVisible();await page.locator('#back').click();await expect(page.locator('#workspace')).toBeVisible();
  const checked=['HTTPS login','server HTML and JS byte identity','account settings native bridge','no remote Tauri API'];
  const query=`/workspace/bugs?project=${project}&bug=${bug.id}&fix=${fix.id}`;
  for(const [name,route,check] of [
   ['tests',`/workspace/tests?project=${project}&run=${bug.run_id}`,()=>expect(frame.getByRole('heading',{name:'Фактические результаты pytest'})).toBeVisible()],
   ['proof',query+'&section=proof',()=>expect(frame.getByText('Повторить тест в том же образе gVisor')).toBeVisible()],
   ['diff',query+'&section=diff',()=>expect(frame.getByLabel('Diff исправления')).toContainText('+    return a + b')],
   ['verification',query+`&run=${fix.verification_id}&section=verification`,()=>expect(frame.getByRole('cell',{name:'2 успешно / 0 с отклонением',exact:true})).toBeVisible()],
   ['report',`/workspace/report?project=${project}&run=${fix.verification_id}`,()=>expect(frame.getByRole('heading').first()).toBeVisible()]
  ]){
   await page.evaluate(route=>listeners['desktop-navigate']({payload:route}),route);await check();await page.screenshot({path:out+'/'+name+'.png'});checked.push('pet navigation '+name);
  }
  await page.locator('#pet-visible').uncheck();await expect(page.locator('#pet-visible')).not.toBeChecked();assert.ok(await page.evaluate(()=>calls.some(c=>c.name==='set_pet_visible'&&c.args.visible===false)));checked.push('pet visibility native contract');
  const after=await get(`/api/projects/${project}/ai-statistics`);assert.equal(after.calls.length,before.calls.length);assert.equal(after.attempts,before.attempts);assert.equal((await get(`/api/projects/${project}/fixes`)).find(f=>f.id===fix.id).applied,false);assert.deepEqual(errors,[]);assert.deepEqual(writes,[]);
  // Expire only this newly created test session, then exercise the real web bridge.
  const logout=await fetch(server+'/auth/logout',{method:'POST',redirect:'manual',headers:{Origin:server,Cookie:'__Host-debugych='+sid}});assert.equal(logout.status,303);
  await frame.evaluate(()=>location.reload());await expect(page.locator('#settings')).toBeVisible({timeout:30000});await expect(page.locator('#status')).toContainText('Сеанс завершён');await expect(page.locator('#workspace')).toBeHidden();checked.push('expired session fails closed into native login');
  const result={role:account.role,checked,newLLMCalls:0,patchApplied:false,errors,writes,nativeWindowLifecycle:'NOT TESTED - IPC contract only'};await fs.writeFile(out+'/result.json',JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close();child.kill();await fetch(server+'/auth/logout',{method:'POST',redirect:'manual',headers:{Origin:server,Cookie:'__Host-debugych='+sid}}).catch(()=>{});}
}
run().catch(e=>{let message=String(e);for(const value of secrets)if(value)message=message.replaceAll(value,'[REDACTED]');console.error(message);process.exitCode=1});
