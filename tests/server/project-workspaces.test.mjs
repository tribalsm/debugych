import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {randomUUID,createHash} from 'node:crypto';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {Accounts} from '../../scripts/web-accounts.mjs';
import {Workspaces} from '../../scripts/project-workspaces.mjs';
import {createGateway} from '../../scripts/serve-server-web.mjs';
const hash=v=>createHash('sha256').update(v).digest('hex');
test('anonymous history persists in SQLite, slides 30 days, claims and expires with quotas',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-history-'));let clock=Date.now();let accounts=new Accounts(path.join(root,'users.db'),{now:()=>clock}),w=new Workspaces(accounts,{now:()=>clock});
 const req={headers:{},socket:{remoteAddress:'127.0.0.1'}};
 try{
  const sid=w.createGuest(req),session=w.session(hash(sid)),pid=randomUUID();w.attach(session,pid);assert.equal(w.owns(session,pid),true);
  accounts.close();accounts=new Accounts(path.join(root,'users.db'),{now:()=>clock});w=new Workspaces(accounts,{now:()=>clock});
  clock+=29*86400000;assert.equal(w.session(hash(sid)).id,session.id);clock+=29*86400000;assert.ok(w.session(hash(sid)));
  const strangerSid=w.createGuest(req),stranger=w.session(hash(strangerSid));assert.equal(w.owns(stranger,pid),false);w.claim(session,{id:'registered'});assert.equal(w.session(hash(sid)),null);assert.equal(w.owns({id:'registered',role:'jury'},pid),true);assert.equal(w.expired().length,0);
  for(let n=0;n<3;n++)w.attach(stranger,randomUUID());assert.throws(()=>w.assertCreate(stranger),{status:429});
  for(let n=0;n<5;n++)w.reserveRun(stranger,req);assert.throws(()=>w.reserveRun(stranger,req),{status:429});
  clock+=31*86400000;assert.equal(w.session(hash(strangerSid)),null);assert.equal(w.expired().length,3);
 }finally{accounts.close();await rm(root,{recursive:true,force:true})}
});
test('HTTP workspace isolation, guest no-AI execution, CSRF, transfer, logout confirmation and cleanup',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-workspace-http-'));await writeFile(path.join(root,'index.html'),'<h1>Workspace</h1>');
 let clock=Date.now();const accounts=new Accounts(':memory:',{now:()=>clock}),projects=[],records=new Map(),calls=[];let busy=false;
 const backend=http.createServer(async(req,res)=>{
  calls.push([req.method,req.url]);let raw='';for await(const c of req)raw+=c;
  const reply=(status,value)=>{res.writeHead(status,{'Content-Type':'application/json'});res.end(JSON.stringify(value))};
  if(req.url==='/api/health')return reply(200,{ai_available:true,execution:'gvisor-python'});
  if(req.url==='/api/storage-usage')return reply(200,{estimated_bytes:0});
  if(req.url==='/api/projects'&&req.method==='GET')return reply(200,projects);
  if(req.url==='/api/projects'&&req.method==='POST'){const p={id:randomUUID(),name:JSON.parse(raw).name,demo:false};projects.push(p);return reply(201,p)}
  if(req.url==='/api/bugs')return reply(200,[...records.values()].filter(r=>r.kind==='bug'));
  const p=projects.find(p=>req.url.startsWith('/api/projects/'+p.id));
  if(p){if(req.method==='DELETE'){if(busy)return reply(409,{});projects.splice(projects.indexOf(p),1);return reply(200,{deleted:true})}if(req.url.endsWith('/runs')&&req.method==='POST'){const r={id:randomUUID(),project_id:p.id,status:'completed'};records.set('/api/runs/'+r.id,r);return reply(202,r)}if(req.url.endsWith('/files'))return reply(200,[]);return reply(200,p)}
  const r=records.get(req.url);if(r)return reply(200,r);reply(404,{});
 });await new Promise(r=>backend.listen(0,'127.0.0.1',r));
 const origin='https://debugych.test',token='t'.repeat(64),demo={version:1,projectId:'public',routes:{'/api/projects':[{id:'public'}],'/api/health':{}}};
 const gateway=createGateway({root,origin,upstream:`http://127.0.0.1:${backend.address().port}`,accounts,teamToken:()=>token,demo,workspaceMode:true,now:()=>clock});await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
 const request=(url,{method='GET',cookie,body,form=false,origin:from=origin}={})=>new Promise((resolve,reject)=>{
  const headers={Host:'debugych.test',Origin:from,Connection:'close'};if(cookie)headers.Cookie=cookie;let raw;
  if(body){raw=form?new URLSearchParams(body).toString():JSON.stringify(body);headers['Content-Type']=form?'application/x-www-form-urlencoded':'application/json'}
  const q=http.request({host:'127.0.0.1',port:gateway.address().port,path:url,method,headers},res=>{let text='';res.on('data',c=>text+=c);res.on('end',()=>{let value;try{value=JSON.parse(text)}catch{}resolve({status:res.statusCode,headers:res.headers,text,value})})});q.on('error',reject);q.end(raw);
 });const cookie=r=>r.headers['set-cookie'][0].split(';')[0];
 try{
  assert.equal((await request('/api/health')).value.guest_mode_available,true);
  assert.equal((await request('/auth/guest',{method:'POST',origin:'https://evil.test'})).status,403);
  const g=await request('/auth/guest',{method:'POST'}),guest=cookie(g);assert.match(g.headers['set-cookie'][0],/Max-Age=2592000/);
  const health=await request('/api/health',{cookie:guest});assert.equal(health.value.ai_available,false);assert.equal(health.value.workspace_mode,'guest');
  const project=await request('/api/projects',{method:'POST',cookie:guest,body:{name:'Own'}});assert.equal(project.status,201);const pid=project.value.id;
  const guest2=cookie(await request('/auth/guest',{method:'POST'}));assert.equal((await request('/api/projects',{cookie:guest2})).value.length,0);
  const beforeDuplicates=calls.length;
  assert.equal((await request('/api/exports?project_id='+pid+'&project_id='+randomUUID(),{cookie:guest})).status,400);
  assert.equal((await request('/api/exports?project_id='+pid+'&%70roject_id='+randomUUID(),{cookie:guest})).status,400);
  assert.equal(calls.length,beforeDuplicates);
  for(const method of ['GET','DELETE','POST'])assert.equal((await request('/api/projects/'+pid,{method,cookie:guest2,body:method==='POST'?{}:undefined})).status,404);
  const bug={id:randomUUID(),project_id:pid,kind:'bug'},run={id:randomUUID(),project_id:pid},tc={id:randomUUID(),project_id:pid};records.set('/api/bugs/'+bug.id,bug);records.set('/api/runs/'+run.id,run);records.set('/api/test-cases/'+tc.id,tc);
  for(const url of ['/api/bugs/'+bug.id,'/api/runs/'+run.id,'/api/test-cases/'+tc.id,'/api/runs/'+run.id+'/artifacts/'+randomUUID(),'/api/exports?project_id='+pid])assert.equal((await request(url,{cookie:guest2})).status,404);
  assert.equal((await request('/api/bugs',{cookie:guest2})).value.length,0);
  const count=calls.length;assert.equal((await request('/api/projects/'+pid+'/autonomous',{method:'POST',cookie:guest,body:{}})).status,403);assert.ok(calls.slice(count).every(c=>!c[1].endsWith('autonomous')));
  assert.equal((await request('/api/projects/'+pid+'/runs',{method:'POST',cookie:guest,origin:'https://evil.test'})).status,403);
  assert.equal((await request('/api/projects/'+pid+'/runs',{method:'POST',cookie:guest,body:{}})).status,202);
  assert.equal((await request('/auth/logout',{method:'POST',cookie:guest,form:true,body:{}})).status,409);
  assert.equal((await request('/api/projects',{cookie:guest})).value.length,1);
  const password='Offline-password-123!';const login=await request('/auth/register',{method:'POST',cookie:guest,form:true,body:{username:'jury-new',password,confirm:password,profile:'jury'}});assert.equal(login.status,303);const member=cookie(login);
  assert.equal((await request('/api/projects',{cookie:member})).value[0].id,pid);assert.equal((await request('/auth/session',{cookie:guest})).value.authenticated,false);
  assert.equal((await request('/api/projects',{method:'POST',cookie:member,body:{name:'Jury owns'}})).status,201);
  // CI deletes its completed temporary project. The next job must not be
  // blocked by the now-cascaded run, while rejected deletes retain admission.
  const ci=await request('/api/projects',{method:'POST',cookie:member,body:{name:'CI temporary'}}),ciid=ci.value.id;
  const ciRun=await request('/api/projects/'+ciid+'/runs',{method:'POST',cookie:member,body:{}});assert.equal(ciRun.status,202);
  records.get('/api/runs/'+ciRun.value.id).status='running';busy=true;
  assert.equal((await request('/api/projects/'+ciid,{method:'DELETE',cookie:member})).status,409);
  assert.equal((await request('/api/projects/'+pid+'/runs',{method:'POST',cookie:member,body:{}})).status,429);
  records.get('/api/runs/'+ciRun.value.id).status='completed';busy=false;
  assert.equal((await request('/api/projects/'+ciid,{method:'DELETE',cookie:member})).status,200);records.delete('/api/runs/'+ciRun.value.id);
  assert.equal((await request('/api/projects/'+pid+'/runs',{method:'POST',cookie:member,body:{}})).status,202);
  const second=await request('/api/projects',{method:'POST',cookie:guest2,body:{name:'Expires'}});busy=true;clock+=31*86400000;
  assert.equal((await request('/auth/session',{cookie:guest2})).value.authenticated,false);
  // A new valid session triggers asynchronous cleanup; busy work is retained.
  const until=async predicate=>{const deadline=Date.now()+5000;while(!predicate()){assert.ok(Date.now()<deadline,'Cleanup deadline');await new Promise(r=>setTimeout(r,20))}};
  const g3=cookie(await request('/auth/guest',{method:'POST'}));await request('/api/health',{cookie:g3});await until(()=>calls.some(c=>c[0]==='DELETE'&&c[1]==='/api/projects/'+second.value.id));assert.ok(projects.some(p=>p.id===second.value.id));busy=false;
  await request('/api/health',{cookie:g3});await until(()=>!projects.some(p=>p.id===second.value.id));assert.ok(projects.some(p=>p.id===pid));
 }finally{gateway.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(r=>gateway.close(r)),new Promise(r=>backend.close(r))]);accounts.close();await rm(root,{recursive:true,force:true})}
});
