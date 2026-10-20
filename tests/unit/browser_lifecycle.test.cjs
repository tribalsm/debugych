const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '../../services/runner/playwright');

function load(name, modules, env = {}) {
  const context = {module:{exports:{}}, process:{env}, console:{log(){}}, Date,
    require: name => modules[name] || require(name)};
  vm.runInNewContext(fs.readFileSync(path.join(root,name),'utf8'), context);
  return context.module.exports;
}

test('job owns launch and shutdown, workers only disconnect, including after errors', async () => {
  const endpoint = 'ws://127.0.0.1:1234/random';
  let launches = 0, shutdowns = 0, disconnects = 0;
  const env = {};
  const setup = load('browser-setup.cjs', {'@playwright/test':{chromium:{
    launchServer: async options => {
      assert.equal(options.host,'127.0.0.1');
      assert.equal(options.chromiumSandbox,false);
      launches++;
      return {wsEndpoint:()=>endpoint,close:async()=>{shutdowns++;}};
    },
  }}}, env);
  const teardown = await setup({projects:[{use:{launchOptions:{chromiumSandbox:false}}}]});
  const fixtures = load('fixtures.cjs', {'@playwright/test':{test:{extend:value=>value}}}, env).test;
  const [worker, options] = fixtures.browser;
  assert.equal(options.scope,'worker');
  const playwright = {chromium:{connect:async address=>{
    assert.equal(address,endpoint);
    return {close:async()=>{disconnects++;}};
  }}};
  await assert.rejects(worker({playwright}, async()=>{throw Error('worker test failed');}), /worker test failed/);
  await worker({playwright}, async()=>{});
  assert.equal(launches,1);
  assert.equal(disconnects,2);
  assert.equal(shutdowns,0);
  await teardown();
  assert.equal(shutdowns,1);
  assert.equal(env.DEBUGYCH_BROWSER_ENDPOINT,undefined);
});

test('missing or nonlocal endpoint fails closed without launching a replacement', async () => {
  for (const endpoint of [undefined, 'ws://external:1234/browser']) {
    const fixtures = load('fixtures.cjs', {'@playwright/test':{test:{extend:value=>value}}},
      {DEBUGYCH_BROWSER_ENDPOINT:endpoint}).test;
    await assert.rejects(fixtures.browser[0]({playwright:{}},async()=>{}), /Missing job-local browser/);
  }
});
