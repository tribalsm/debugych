const base = require('@playwright/test');
const fs = require('node:fs');
const crypto = require('node:crypto');
const test = base.test.extend({
  browser: [async ({playwright}, use) => {
    const endpoint = process.env.DEBUGYCH_BROWSER_ENDPOINT;
    if (!endpoint || !endpoint.startsWith('ws://127.0.0.1:')) throw Error('Missing job-local browser');
    const browser = await playwright.chromium.connect(endpoint);
    try {await use(browser);} finally {
      // For connect(), close disconnects this worker, leaving job ownership in
      // globalSetup. Playwright still creates and closes a fresh context/test.
      await browser.close();
    }
  }, {scope:'worker'}],
  page: async ({page}, use, info) => {
    const observations = {console:[], page_errors:[], worker_index:info.workerIndex};
    page.on('console', message => {if(observations.console.length<30) observations.console.push(message.text().slice(0,500));});
    page.on('pageerror', error => {if(observations.page_errors.length<10) observations.page_errors.push(error.message.slice(0,1000));});
    // Container has no network. This also blocks browser requests to arbitrary origins.
    await page.context().route('**/*', route => {
      const url = new URL(route.request().url());
      return url.origin==='http://127.0.0.1:4173' ? route.continue() : route.abort('blockedbyclient');
    });
    try {await use(page);} finally {
      const id = crypto.createHash('sha256').update(info.testId).digest('hex').slice(0,24);
      try {
        const screenshot = await page.screenshot({timeout:3000,fullPage:false});
        if(screenshot.length<=400000) await info.attach('screenshot',{body:screenshot,contentType:'image/png'});
      } catch(error) {observations.screenshot_error=String(error).slice(0,200);}
      try {
        const coverage = await page.evaluate(()=>globalThis.__coverage__||null);
        if(coverage) fs.writeFileSync(`/tmp/job/reports/coverage-${id}.json`,JSON.stringify(coverage));
      } catch {}
      await info.attach('browser-observations',{body:Buffer.from(JSON.stringify(observations)),contentType:'application/json'});
    }
  }
});
module.exports = {...base,test};
