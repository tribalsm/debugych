import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtemp,writeFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createGateway} from '../../scripts/serve-server-web.mjs';

test('domain migration preserves exact Host/Origin binding on both approved origins',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-origins-'));await writeFile(path.join(root,'index.html'),'<h1>Workspace</h1>');
 const token='t'.repeat(64),primary='https://new.test:9443',legacy='https://old.test:9443';let calls=0;
 const backend=http.createServer((req,res)=>{calls++;res.writeHead(req.headers.authorization==='Bearer '+token?200:401,{'Content-Type':'application/json'});res.end('{}')});await new Promise(r=>backend.listen(0,'127.0.0.1',r));
 const options={root,origin:primary,upstream:`http://127.0.0.1:${backend.address().port}`};
 for(const aliases of [['http://old.test'],['https://old.test/path'],['https://old.test?x=1'],['https://user@old.test'],['https://*.old.test'],[legacy,legacy,legacy],'https://old.test'])assert.throws(()=>createGateway({...options,aliases}));
 const gateway=createGateway({...options,aliases:[legacy]});await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
 const request=(host,origin,cookie)=>new Promise((resolve,reject)=>{
  const headers={Host:host,Origin:origin,'Content-Type':'application/x-www-form-urlencoded',Connection:'close'};if(cookie)headers.Cookie=cookie;
  const req=http.request({host:'127.0.0.1',port:gateway.address().port,path:cookie?'/api/projects':'/auth/login',method:'POST',headers},res=>{res.resume();res.on('end',()=>resolve({status:res.statusCode,cookie:res.headers['set-cookie']?.[0]}))});req.on('error',reject);req.end(cookie?'{}':new URLSearchParams({token}).toString());
 });
 try{
  for(const origin of [primary,legacy]){
   const host=new URL(origin).host,other=origin===primary?legacy:primary;
   const login=await request(host,origin);assert.equal(login.status,303);assert.match(login.cookie,/Secure; HttpOnly; SameSite=Strict/);assert.ok(!login.cookie.includes('Domain='));
   const cookie=login.cookie.split(';')[0],before=calls;
   assert.equal((await request(host,other,cookie)).status,403);assert.equal(calls,before);
   assert.equal((await request(host,'https://evil.test',cookie)).status,403);assert.equal(calls,before);
   assert.equal((await request(host,origin,cookie)).status,200);
  }
  const before=calls;assert.equal((await request('attacker.test:9443',primary)).status,403);assert.equal(calls,before);
 }finally{gateway.closeAllConnections();backend.closeAllConnections();await Promise.all([new Promise(r=>gateway.close(r)),new Promise(r=>backend.close(r))]);await rm(root,{recursive:true,force:true})}
});
