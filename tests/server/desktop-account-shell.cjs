// Headless contract tests of the real native shell; not Windows UI automation.
const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs/promises'),path=require('node:path');
const {chromium,expect}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
async function fixture(saved=false){
 const browser=await chromium.launch({headless:true}),context=await browser.newContext(),page=await context.newPage();
 await page.route('**/*',async route=>{const url=new URL(route.request().url());if(url.hostname==='desktop.test'){const file=url.pathname==='/'?'index.html':url.pathname.slice(1);assert.ok(['index.html','shell.js','shell.css'].includes(file));return route.fulfill({body:await fs.readFile(path.resolve(__dirname,'../../apps/desktop/shell',file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'})}return route.fulfill({body:'<!doctype html><h1>Contract workspace</h1>',contentType:'text/html'})});
 await page.addInitScript(saved=>{
  window.calls=[];window.listeners={};window.savedAccount=saved;window.accountUsername='jury-contract';
  window.cfg={mode:'remote',api_url:'https://debugych.89-22-232-119.nip.io:9443',backend_root:'',route_ip:'',config_directory:'Contract profile'};
  window.ctx={backendUrl:cfg.api_url,frontendUrl:'',projectId:'',revision:0,petVisible:false};
  window.__TAURI__={event:{listen:async(n,f)=>{listeners[n]=f}},core:{invoke:async(n,args)=>{
   calls.push({name:n,args});
   if(n==='get_config')return {...cfg};if(n==='get_desktop_context')return {...ctx};if(n==='startup_status')return window.staleStatus||'';
   if(n==='account_info')return {saved:savedAccount,username:savedAccount?accountUsername:'',role:savedAccount?'jury':''};
   if(n==='save_config'){cfg={...cfg,...args.config};ctx.backendUrl=cfg.api_url;ctx.revision++;return;}
   if(n==='account_sign_in'){if(args.password==='wrong-offline-password')throw 'Неверный логин или пароль';savedAccount=true;accountUsername=args.username;ctx.projectId='';ctx.revision++;return {saved:true,username:accountUsername,role:'jury'}}
   if(n==='account_sign_out'){savedAccount=false;ctx.projectId='';ctx.revision++;return;}
   if(n==='start_application'){if(cfg.mode==='remote'&&!savedAccount)throw 'Войдите в аккаунт сайта в настройках подключения';return 'http://127.0.0.1:45678/'}
   throw Error('Unexpected native command: '+n);
  }}};
 },saved);
 await page.goto('https://desktop.test/');
 return {page,browser,context};
}
test('fresh Desktop asks for website credentials and never writes the password into configuration',async()=>{
 const {page,browser}=await fixture();try{
  await expect(page.locator('#settings')).toBeVisible();await expect(page.locator('#server-token')).toBeHidden();
  await page.screenshot({path:path.resolve(__dirname,'../../outputs/server10/desktop-account-connection.png'),fullPage:true});await page.locator('#account-username').fill('jury-contract');await page.locator('#account-password').fill('offline-contract-password');await page.locator('#account-password').press('Enter');await expect(page.locator('#workspace')).toBeVisible();await expect(page.locator('#account-password')).toHaveValue('');
  const calls=await page.evaluate(()=>calls);assert.equal(calls.filter(c=>c.name==='account_sign_in').length,1);assert.ok(calls.filter(c=>c.name==='save_config').every(c=>!JSON.stringify(c.args).includes('offline-contract-password')));assert.equal(calls.filter(c=>c.name==='set_server_token').length,0);assert.ok(!(await page.locator('#workspace').getAttribute('src')).includes('password'));assert.ok(!(await page.evaluate(()=>JSON.stringify(localStorage))).includes('offline-contract-password'));
 }finally{await browser.close()}
});
test('wrong credentials leave the workspace hidden and never fall back to an owner key',async()=>{
 const {page,browser}=await fixture();try{await expect(page.locator('#settings')).toBeVisible();await page.evaluate(()=>window.staleStatus='Old ready status');await page.locator('#account-username').fill('jury-contract');await page.locator('#account-password').fill('wrong-offline-password');await page.locator('#save').click();await expect(page.locator('#status')).toContainText('Неверный логин или пароль');await page.waitForTimeout(850);await expect(page.locator('#status')).toContainText('Неверный логин или пароль');await expect(page.locator('#workspace')).toBeHidden();await expect(page.locator('#account-password')).toHaveValue('');assert.equal(await page.evaluate(()=>calls.filter(c=>c.name==='set_server_token').length),0);}finally{await browser.close()}
});
test('saved session resumes without a password; logout clears the old workspace',async()=>{
 const {page,browser}=await fixture(true);try{await expect(page.locator('#workspace')).toBeVisible();assert.equal(await page.evaluate(()=>calls.filter(c=>c.name==='account_sign_in').length),0);await page.locator('#connection').click();await expect(page.locator('#account-username')).toHaveValue('jury-contract');await page.locator('#account-sign-out').click();await expect(page.locator('#status')).toContainText('Вы вышли');await expect(page.locator('#workspace')).toBeHidden();await expect(page.locator('#back')).toBeHidden();await expect(page.locator('#account-password')).toHaveValue('');await expect(page.locator('#account-sign-out')).toBeDisabled();assert.equal(await page.locator('#workspace').getAttribute('src'),'about:blank');}finally{await browser.close()}
});
test('only the bound workspace can request a new login after session expiry',async()=>{
 const {page,browser}=await fixture(true);try{
  await expect(page.locator('#workspace')).toBeVisible();const frame=page.frames().find(f=>f.url().startsWith('http://127.0.0.1:45678'));assert.ok(frame);
  await frame.evaluate(()=>parent.postMessage({type:'debugych-desktop-auth-required',session:'forged'},'https://desktop.test'));await expect(page.locator('#workspace')).toBeVisible();
  await frame.evaluate(()=>parent.postMessage({type:'debugych-desktop-auth-required',session:new URLSearchParams(location.search).get('desktop_session')},'https://desktop.test'));
  await expect(page.locator('#settings')).toBeVisible();await expect(page.locator('#status')).toContainText('Сеанс завершён');await expect(page.locator('#workspace')).toBeHidden();await expect(page.locator('#back')).toBeHidden();
 }finally{await browser.close()}
});
test('typing a different username without its password does not reuse the previous account',async()=>{
 const {page,browser}=await fixture(true);try{await expect(page.locator('#workspace')).toBeVisible();await page.locator('#connection').click();await expect(page.locator('#account-username')).toHaveValue('jury-contract');await page.locator('#account-username').fill('different-contract');await page.locator('#save').click();await expect(page.locator('#status')).toContainText('Введите пароль');await expect(page.locator('#workspace')).toBeHidden();assert.equal(await page.evaluate(()=>calls.filter(c=>c.name==='start_application').length),1);assert.equal(await page.evaluate(()=>calls.filter(c=>c.name==='account_sign_in').length),0);}finally{await browser.close()}
});
