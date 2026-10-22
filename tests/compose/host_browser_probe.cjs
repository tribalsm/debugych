// Host E2E infrastructure probe. No project execution and no provider requests.
const assert = require('node:assert/strict');
const {chromium} = require('../../apps/web/node_modules/@playwright/test');
let browser;
const channel=process.env.PLAYWRIGHT_HOST_CHANNEL||'chromium';
const deadline = setTimeout(() => {console.error('Host browser probe exceeded 30s');process.exit(1);},30000);
(async()=>{
  const start=Date.now();
  browser=await chromium.launch({channel,headless:true,timeout:10000});
  for(let i=0;i<40;i++) {
    const context=await browser.newContext();
    const page=await context.newPage();
    await page.setContent('<h1>Context '+i+'</h1>');
    assert.equal(await page.locator('h1').textContent(),'Context '+i);
    await context.close();
  }
  console.log(JSON.stringify({contexts:40,passed:true,browser:browser.version(),channel,duration_ms:Date.now()-start,llm_requests:0}));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{
  try {if(browser)await browser.close();}finally{clearTimeout(deadline);}
});
