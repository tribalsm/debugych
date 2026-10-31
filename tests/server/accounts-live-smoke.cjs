// Real HTTPS, isolated QA accounts, no AI calls or project mutations.
const {chromium,expect}=require(process.env.DEBUGYCH_PLAYWRIGHT_MODULE||'@playwright/test');
const fs=require('node:fs/promises'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const secrets=new Set();
(async()=>{
 let raw='';for await(const chunk of process.stdin)raw+=chunk;const input=JSON.parse(raw);raw='';secrets.add(input.token);for(const u of input.bootstrap)secrets.add(u.password);
 const base='https://debugych.46-226-161-120.sslip.io:9443',out='outputs/server10/accounts-live';await fs.mkdir(out,{recursive:true});
 const id=Date.now().toString(36),juryName='qa-jury-'+id,teamName='qa-team-'+id,password=crypto.randomBytes(24).toString('base64url'),replacement=crypto.randomBytes(24).toString('base64url');secrets.add(password);secrets.add(replacement);
 await fs.writeFile(out+'/qa-users.json',JSON.stringify([juryName,teamName]));
 const browser=await chromium.launch({headless:true}),context=await browser.newContext({viewport:{width:1280,height:1000}}),page=await context.newPage(),owner=await browser.newContext();let stale;
 const errors=[],blocked=[];page.on('pageerror',e=>errors.push(e.message));
 await page.route('**/*',r=>{const u=new URL(r.request().url());if(!['GET','HEAD','OPTIONS'].includes(r.request().method())&&!(u.origin===base&&['/auth/register','/auth/sign-in','/auth/password','/auth/logout'].includes(u.pathname))){blocked.push(u.pathname);return r.abort()}return r.continue()});
 const post=(ctx,url,form)=>ctx.request.post(base+url,{headers:{Origin:base},form,maxRedirects:0});
 const state=async ctx=>(await ctx.request.get(base+'/auth/session')).json();
 try{
  const csrf=await context.request.post(base+'/auth/register',{headers:{Origin:'https://evil.invalid'},form:{username:'must-not-create',password,confirm:password}});assert.equal(csrf.status(),403);
  await page.goto(base+'/auth/register');await expect(page.getByRole('heading',{name:'Создайте аккаунт'})).toBeVisible();await page.screenshot({path:out+'/registration.png'});
  await page.getByLabel('Логин',{exact:true}).fill(juryName);await page.getByLabel('Пароль, от 12 символов',{exact:true}).fill(password);await page.getByLabel('Повторите пароль',{exact:true}).fill(password);await page.getByLabel('Профиль',{exact:true}).selectOption('jury');await page.getByRole('button',{name:'Зарегистрироваться',exact:true}).click();await expect(page).toHaveURL(base+'/auth/account');assert.equal((await state(context)).role,'jury');await page.screenshot({path:out+'/jury-profile.png'});
  assert.equal((await context.request.get(base+'/api/projects')).headers()['x-debugych-public-demo'],'1');assert.equal((await context.request.get(base+'/api/projects/78167145-424b-48a8-b3f9-6eefa284f3c3/source-archive')).status(),404);
  assert.equal((await post(context,'/api/companion/ask',{question:'must not run'})).status(),403);assert.equal((await post(context,'/auth/invitations',{role:'admin'})).status(),403);
  assert.equal((await post(context,'/auth/logout',{})).status(),303);
  const jury=input.bootstrap.find(u=>u.role==='jury');assert.equal((await post(context,'/auth/sign-in',{username:jury.username,password:jury.password})).status(),303);assert.ok((await state(context)).role==='jury'&&(await state(context)).mustChange);assert.equal((await post(context,'/auth/logout',{})).status(),303);
  assert.equal((await post(owner,'/auth/login',{token:input.token})).status(),303);const grant=await post(owner,'/auth/invitations',{role:'team'});assert.equal(grant.status(),200);const invitation=(await grant.text()).match(/id="invitation-code">([a-f0-9]{64})</)[1];secrets.add(invitation);
  assert.equal((await post(context,'/auth/register',{username:teamName,password,confirm:password,profile:'viewer',invitation})).status(),303);assert.equal((await state(context)).role,'team');
  await page.goto(base+'/auth/account');await expect(page.getByRole('heading',{name:teamName,exact:true})).toBeVisible();await expect(page.getByText('Команда',{exact:true})).toBeVisible();await page.screenshot({path:out+'/team-profile.png'});
  assert.equal((await context.request.get(base+'/api/projects/78167145-424b-48a8-b3f9-6eefa284f3c3/source-archive')).status(),200);assert.equal((await post(context,'/auth/invitations',{role:'admin'})).status(),403);
  stale=await browser.newContext();await stale.addCookies(await context.cookies(base));
  await page.getByText('Изменить пароль',{exact:true}).click();await page.getByLabel('Текущий пароль',{exact:true}).fill(password);await page.getByLabel('Новый пароль',{exact:true}).fill(replacement);await page.getByLabel('Повторите новый пароль',{exact:true}).fill(replacement);await page.getByRole('button',{name:'Изменить пароль и завершить сеансы'}).click();await expect(page).toHaveURL(base+'/auth/login');assert.equal((await state(stale)).authenticated,false);
  await page.getByLabel('Логин',{exact:true}).fill(teamName);await page.getByLabel('Пароль',{exact:true}).fill(replacement);await page.getByRole('button',{name:'Войти',exact:true}).click();await expect(page).toHaveURL(base+'/auth/account');assert.equal((await state(context)).role,'team');assert.equal((await post(context,'/auth/logout',{})).status(),303);
  const admin=input.bootstrap.find(u=>u.role==='admin');assert.equal((await post(context,'/auth/sign-in',{username:admin.username,password:admin.password})).status(),303);const adminState=await state(context);assert.ok(adminState.role==='admin'&&adminState.mustChange);assert.equal((await context.request.get(base+'/api/projects')).headers()['x-debugych-public-demo'],'1');assert.equal((await post(context,'/auth/invitations',{role:'admin'})).status(),403);assert.equal((await post(context,'/auth/logout',{})).status(),303);
  assert.equal((await post(context,'/auth/register',{username:'must-not-escalate-'+id,password,confirm:password,role:'admin'})).status(),403);
  assert.equal((await post(owner,'/auth/logout',{})).status(),303);assert.deepEqual(errors,[]);assert.deepEqual(blocked,[]);
  const report={classification:'LIVE_ACCOUNT_WORKFLOW_PASS',juryRegistration:true,juryReadOnly:true,teamInvitation:true,teamAuthenticatedBackend:true,teamCannotInviteAdmins:true,passwordChange:true,oldSessionsRevoked:true,bootstrapAccountsConfirmed:true,bootstrapPasswordChangeRequired:true,csrfDenied:true,roleForgeryDenied:true,projectWrites:0,paidLLMRequests:0,browserErrors:errors};await fs.writeFile(out+'/result.json',JSON.stringify(report,null,2));console.log(JSON.stringify(report));
 }finally{await browser.close()}
})().catch(e=>{let text=String(e);for(const value of secrets)text=text.replaceAll(value,'[REDACTED]');console.error(text);process.exitCode=1});
