import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createGateway} from '../../scripts/serve-server-web.mjs';

test('browser sessions fail closed, preserve native Bearer, bound lifetime and never expose the token',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-web-session-'));
 await writeFile(path.join(root,'index.html'),'<h1>Existing workspace fixture</h1>');
 const token='offline-only-'+ 'a'.repeat(50);let enabled=true,calls=0,headersSeen;
 const backend=http.createServer((req,res)=>{calls++;headersSeen=req.headers;res.writeHead(enabled&&req.headers.authorization==='Bearer '+token?200:401,{'Content-Type':'application/json'});res.end(JSON.stringify({status:'ok'}))});
 await new Promise(r=>backend.listen(0,'127.0.0.1',r));let clock=1000;
 const origin='https://debugych.test:9443';
 const gateway=createGateway({root,origin,upstream:`http://127.0.0.1:${backend.address().port}`,now:()=>clock,idleMs:100,maxAgeMs:1000});
 await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
 const request=(url,method='GET',headers={},body='')=>new Promise((resolve,reject)=>{
  const req=http.request({host:'127.0.0.1',port:gateway.address().port,path:url,method,headers:{Host:'debugych.test:9443',Connection:'close',...headers}},res=>{let text='';res.setEncoding('utf8');res.on('data',chunk=>text+=chunk);res.on('end',()=>{assert.ok(!text.includes(token));resolve({status:res.statusCode,headers:res.headers,text})})});req.on('error',reject);req.end(body);
 });
 const form={Origin:origin,'Content-Type':'application/x-www-form-urlencoded'};
 const login=()=>request('/auth/login','POST',form,'token='+token);
 try{
  assert.equal((await request('/')).headers.location,'/auth/login');
  assert.equal((await request('/api/projects')).status,401);assert.equal(calls,0);
  assert.equal((await request('/auth/login')).status,200);
  assert.equal((await request('/auth/login','POST',{...form,Origin:'https://evil.test'},'token='+token)).status,403);assert.equal(calls,0);
  assert.equal((await request('/auth/login','POST',form,'token=wrong')).status,401);
  const accepted=await login();assert.equal(accepted.status,303);
  const cookie=accepted.headers['set-cookie'][0];for(const flag of ['Secure','HttpOnly','SameSite=Strict','Path=/'])assert.ok(cookie.includes(flag));assert.ok(!cookie.includes(token));
  const auth={Cookie:cookie.split(';')[0]};
  assert.equal((await request('/', 'GET',auth)).status,200);
  assert.equal((await request('/api/projects','GET',auth)).status,200);assert.equal(headersSeen.cookie,undefined);
  let n=calls;
  assert.equal((await request('/api/projects','POST',{...auth,Origin:'https://evil.test'},'{}')).status,403);assert.equal(calls,n);
  assert.equal((await request('/api/projects','POST',auth,'{}')).status,403);assert.equal(calls,n);
  assert.equal((await request('/api/projects','POST',{...auth,Origin:origin,'Content-Type':'application/json'},'{}')).status,200);
  assert.equal((await request('/api/projects','GET',{Authorization:'Bearer '+token})).status,200);
  assert.equal((await request('/api/projects','GET',{Authorization:'Bearer invalid',...auth})).status,401);
  assert.equal((await request('/api/projects','GET',{...auth,'Sec-Fetch-Site':'cross-site'})).status,403);
  assert.equal((await request('/%2e%2e/private','GET',auth)).status,400);
  assert.equal((await request('/','GET',{...auth,Host:'evil.test'})).status,403);
  enabled=false;const revoked=await request('/api/projects','GET',auth);assert.equal(revoked.status,401);assert.ok(revoked.headers['set-cookie'][0].includes('Max-Age=0'));enabled=true;
  assert.equal((await request('/api/projects','GET',auth)).status,401);
  let fresh=(await login()).headers['set-cookie'][0].split(';')[0];clock+=101;
  assert.equal((await request('/api/projects','GET',{Cookie:fresh})).status,401);
  fresh=(await login()).headers['set-cookie'][0].split(';')[0];
  for(let i=0;i<12;i++){clock+=80;assert.equal((await request('/api/projects','GET',{Cookie:fresh})).status,200)}
  clock+=80;assert.equal((await request('/api/projects','GET',{Cookie:fresh})).status,401);
  assert.equal((await request('/api/projects','GET',{Cookie:'__Host-debugych=forged'})).status,401);
  assert.equal((await request('/auth/login','POST',form,'token='+token+'&padding='+'x'.repeat(2048))).status,413);
  fresh=(await login()).headers['set-cookie'][0].split(';')[0];
  assert.equal((await request('/auth/account','GET',{Cookie:fresh})).status,200);
  assert.equal((await request('/auth/logout','GET',{Cookie:fresh})).status,405);
  assert.equal((await request('/auth/logout','POST',{Cookie:fresh,Origin:'https://evil.test'})).status,403);
  assert.equal((await request('/auth/logout','POST',{Cookie:fresh,Origin:origin})).status,303);
  assert.equal((await request('/api/projects','GET',{Cookie:fresh})).status,401);
  for(let i=0;i<8;i++)await request('/auth/login','POST',{...form,'X-Real-IP':'test-rate-limit'},'token=bad');
  assert.equal((await request('/auth/login','POST',{...form,'X-Real-IP':'test-rate-limit'},'token=bad')).status,429);
 }finally{gateway.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(r=>gateway.close(r)),new Promise(r=>backend.close(r))]);await rm(root,{recursive:true,force:true})}
});

test('public demo serves only its frozen allowlist and never forwards anonymous requests',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-public-demo-'));await writeFile(path.join(root,'index.html'),'<h1>Existing workspace fixture</h1>');
 let calls=0;const backend=http.createServer((_req,res)=>{calls++;res.writeHead(200,{'Content-Type':'application/json'});res.end('{"owner":true}')});await new Promise(r=>backend.listen(0,'127.0.0.1',r));
 const projectId='78167145-424b-48a8-b3f9-6eefa284f3c3';
 const demo={version:1,projectId,routes:{'/api/projects':[{id:projectId,name:'Public control'}],['/api/projects/'+projectId+'/runs']:[{id:'saved-run',status:'completed'}]}};
 const gateway=createGateway({root,origin:'https://debugych.test',upstream:`http://127.0.0.1:${backend.address().port}`,demo});await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
 const request=(url,method='GET',headers={})=>new Promise((resolve,reject)=>{const req=http.request({host:'127.0.0.1',port:gateway.address().port,path:url,method,headers:{Host:'debugych.test',Connection:'close',...headers}},res=>{let body='';res.on('data',c=>body+=c);res.on('end',()=>resolve({status:res.statusCode,body,headers:res.headers}))});req.on('error',reject);req.end()});
 try{
  assert.equal((await request('/')).status,200);assert.equal((await request('/auth/login')).headers.location,'/');assert.equal((await request('/auth/login?owner=1')).status,200);
  const projects=await request('/api/projects');assert.deepEqual(JSON.parse(projects.body),demo.routes['/api/projects']);assert.equal(projects.headers['x-debugych-public-demo'],'1');assert.equal(projects.headers['set-cookie'],undefined);
  assert.equal((await request('/api/projects/'+projectId+'/runs')).status,200);
  for(const url of ['/api/projects/private','/api/bugs/private','/api/projects?include=private','/api/ai/status','/api/projects/'+projectId+'/source-archive','/docs','/openapi.json'])assert.equal((await request(url)).status,404,url);
  for(const method of ['POST','PATCH','PUT','DELETE'])for(const url of ['/api/projects','/api/projects/'+projectId+'/autonomous','/api/bugs/any/verify-fix','/api/bugs/any/apply-fix','/api/companion/ask'])assert.equal((await request(url,method)).status,403,method+' '+url);
  assert.equal(calls,0);
  assert.equal((await request('/api/projects','GET',{Authorization:'Bearer '+'a'.repeat(64)})).status,200);assert.equal(calls,1);
  assert.equal((await request('/api/projects','GET',{Authorization:'Bearer invalid'})).status,401);assert.equal(calls,1);
 }finally{gateway.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(r=>gateway.close(r)),new Promise(r=>backend.close(r))]);await rm(root,{recursive:true,force:true})}
});
