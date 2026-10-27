// Contract browser tests, not native/installer or live AI evidence.
const {test,expect}=require('@playwright/test');
const fs=require('node:fs/promises');const path=require('node:path');
test.beforeEach(async({page})=>{
 await page.route('**/*',async route=>{const u=new URL(route.request().url());if(u.hostname==='desktop.test'){const file=u.pathname==='/'?'index.html':u.pathname.slice(1);if(!['index.html','shell.js','shell.css'].includes(file))return route.abort();return route.fulfill({body:await fs.readFile(path.join('/work/pet/web/desktop-shell',file)),contentType:file.endsWith('.js')?'text/javascript':file.endsWith('.css')?'text/css':'text/html'})}return route.fulfill({body:'<!doctype html><title>Contract workspace</title><p>Saved workspace fixture</p>',contentType:'text/html'})});
 await page.addInitScript(()=>{
  window.nativeCalls=[];window.listeners={};window.failStart=false;
  window.ctx={backendUrl:'http://127.0.0.1:8000',frontendUrl:'',projectId:'',revision:0,petVisible:false};
  window.cfg={mode:'local',api_url:ctx.backendUrl,backend_root:'',config_directory:'Contract profile'};
  window.__TAURI__={event:{listen:async(name,fn)=>{listeners[name]=fn;return()=>{}}},core:{invoke:async(name,args)=>{
   nativeCalls.push({name,args});
   if(name==='get_config')return {...cfg};if(name==='get_desktop_context')return {...ctx};if(name==='startup_status')return '';
   if(name==='start_application'){if(failStart||cfg.mode==='remote')throw 'Сервер недоступен. Локальный стек не изменялся.';return 'http://127.0.0.1:45678/'}
   if(name==='save_config'){cfg={...cfg,...args.config};ctx={...ctx,backendUrl:cfg.api_url,projectId:'',revision:ctx.revision+1};return;}
   if(name==='set_pet_visible'){ctx={...ctx,petVisible:args.visible,revision:ctx.revision+1};return {...ctx}}
   if(name==='environment_diagnostics')return [{name:'API',status:'pass',detail:'Backend отвечает'},{name:'AI-провайдер',status:'warning',detail:'<img src=x onerror=alert(1)> Платный запрос не выполнялся'}];
   throw Error('Unexpected native command '+name);
  }}};
 });
 await page.goto('https://desktop.test/');await expect(page.locator('#workspace')).toBeVisible();
});
test('readiness is explicit and provider text cannot inject markup',async({page})=>{
 await page.locator('#diagnostics').click();await expect(page.locator('.diagnostic')).toHaveCount(2);await expect(page.locator('.diagnostic.warning')).toContainText('Платный запрос не выполнялся');await expect(page.locator('#diagnostic-results img')).toHaveCount(0);await expect(page.locator('#diagnostics')).toBeEnabled();await page.locator('#back').click();await expect(page.locator('#workspace')).toBeVisible();
});
test('remote failure clears old workspace and stays retryable',async({page})=>{
 await page.locator('#connection').click();await page.locator('#mode').selectOption('remote');await expect(page.locator('#root-label')).toBeHidden();await page.locator('#api').fill('https://release.invalid');await page.locator('#save').click();await expect(page.locator('#status')).toContainText('Сервер недоступен');await expect(page.locator('#workspace')).toBeHidden();await expect(page.locator('#retry')).toBeVisible();expect(await page.locator('#workspace').getAttribute('src')).toBe('about:blank');expect(await page.evaluate(()=>nativeCalls.filter(c=>c.name==='save_config')[0].args.config.mode)).toBe('remote');
});
test('local retry returns the real workspace only after native startup succeeds',async({page})=>{
 await page.evaluate(()=>{failStart=true});await page.locator('#connection').click();await page.locator('#save').click();await expect(page.locator('#retry')).toBeVisible();await expect(page.locator('#workspace')).toBeHidden();await page.evaluate(()=>{failStart=false});await page.locator('#retry').click();await expect(page.locator('#workspace')).toBeVisible();await expect(page.locator('#startup')).toBeHidden();
});
test('pet visibility follows the shared native context, including external hide',async({page})=>{
 await page.locator('#pet-visible').check();await expect(page.locator('#pet-visible')).toBeChecked();await page.evaluate(()=>{ctx={...ctx,revision:ctx.revision+1,petVisible:false};listeners['desktop-context']({payload:ctx})});await expect(page.locator('#pet-visible')).not.toBeChecked();expect(await page.evaluate(()=>nativeCalls.filter(c=>c.name==='set_pet_visible').length)).toBe(1);
});
