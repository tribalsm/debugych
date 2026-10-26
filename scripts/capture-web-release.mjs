// Read-only browser recording of saved real records. Never starts AI or applies a patch.
import {chromium} from '../apps/web/node_modules/playwright/index.mjs';
import {mkdir,readFile} from 'node:fs/promises';
const base=process.env.PLAYWRIGHT_BASE_URL||'http://127.0.0.1:8798';
const out=new URL('../outputs/web-integration/',import.meta.url).pathname.replace(/^\/([A-Z]:)/,'$1');
await mkdir(out,{recursive:true});
const evidence=JSON.parse(await readFile(out+'/free-verify.json','utf8'));
const browser=await chromium.launch();
const context=await browser.newContext({viewport:{width:1600,height:1000},recordVideo:{dir:out+'/presentation',size:{width:1600,height:1000}}});
const page=await context.newPage();
const route=`project=${evidence.projectId}`;
const bug='45a3e289-39c2-4bcd-b504-5e1ec62cb394',fix='c41ceb12-55b9-4d85-87a3-332eba94717e',run='93bf09e7-c557-4575-82a4-9c92a30e2a6a';
for(const [name,url] of [['dashboard','/'],['test-studio',`/#/workspace/tests?${route}&run=${run}`],['bug-proof',`/#/workspace/bugs?${route}&bug=${bug}&run=${run}&section=proof`],['diff',`/#/workspace/bugs?${route}&bug=${bug}&fix=${fix}&section=diff`],['verified',`/#/workspace/bugs?${route}&bug=${bug}&fix=${fix}&section=verification&run=${evidence.newVerification}`]]){
 await page.goto(base+url);await page.getByRole('status',{name:'Загружаем рабочее пространство'}).waitFor({state:'hidden'});
 await page.locator('.skeleton').first().waitFor({state:'hidden'});await page.getByText('LLM настроен',{exact:true}).waitFor();
 await page.waitForTimeout(3500);await page.screenshot({path:out+'/'+name+'.png',fullPage:true});
}
await context.close();await browser.close();
console.log('Saved real records recorded. The earlier fresh free Verify is documented in free-verify.json.');
