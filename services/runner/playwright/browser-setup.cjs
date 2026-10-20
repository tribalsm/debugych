const {chromium} = require('@playwright/test');

// One browser per disposable job, not per Playwright worker. Failed assertions
// restart workers; relaunching Chromium each time wastes the fixed suite budget.
// globalSetup and its teardown are both covered by Playwright's globalTimeout.
module.exports = async config => {
  const started = Date.now();
  const browser = await chromium.launchServer({
    ...config.projects[0].use.launchOptions,
    headless: true,
    host: '127.0.0.1',
  });
  process.env.DEBUGYCH_BROWSER_ENDPOINT = browser.wsEndpoint();
  console.log('DEBUGYCH_BROWSER_READY_MS=' + (Date.now() - started));
  return async () => {
    delete process.env.DEBUGYCH_BROWSER_ENDPOINT;
    await browser.close();
  };
};
