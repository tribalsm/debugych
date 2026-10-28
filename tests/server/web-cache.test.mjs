import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,writeFile,mkdir,rm} from 'node:fs/promises';
import path from 'node:path';
import {tmpdir} from 'node:os';
import {createGateway} from '../../scripts/serve-server-web.mjs';
import http from 'node:http';

test('server updates revalidate mutable resources while hashed bundles stay immutable',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-cache-'));
 await mkdir(path.join(root,'assets'));await writeFile(path.join(root,'index.html'),'<h1>One</h1>');await writeFile(path.join(root,'config.json'),'one');await writeFile(path.join(root,'assets','index-12345678.js'),'bundle');
 const gateway=createGateway({root,origin:'https://debugych.test',upstream:'http://127.0.0.1:1',demo:{version:1,projectId:'cache-fixture',routes:{'/api/projects':[{id:'cache-fixture'}]}}});await new Promise(r=>gateway.listen(0,'127.0.0.1',r));
 const get=(p,headers={})=>new Promise((resolve,reject)=>{const req=http.get({host:'127.0.0.1',port:gateway.address().port,path:p,headers:{Host:'debugych.test',Connection:'close',...headers}},res=>{let body='';res.setEncoding('utf8');res.on('data',s=>body+=s);res.on('end',()=>resolve({status:res.statusCode,headers:new Headers(res.headers),text:async()=>body}))});req.on('error',reject)});
 try{
  let r=await get('/');assert.equal(r.status,200);assert.equal(r.headers.get('cache-control'),'no-store');assert.ok((await r.text()).includes('One'));
  await writeFile(path.join(root,'index.html'),'<h1>Updated</h1>');r=await get('/');assert.ok((await r.text()).includes('Updated'));
  r=await get('/assets/index-12345678.js');assert.equal(r.headers.get('cache-control'),'public, max-age=31536000, immutable');await r.text();
  r=await get('/config.json');assert.equal(r.headers.get('cache-control'),'private, max-age=0, must-revalidate');const etag=r.headers.get('etag');assert.ok(etag);await r.text();
  assert.equal((await get('/config.json',{'If-None-Match':etag})).status,304);
  await writeFile(path.join(root,'config.json'),'updated-version');r=await get('/config.json',{'If-None-Match':etag});assert.equal(r.status,200);assert.notEqual(r.headers.get('etag'),etag);assert.equal(await r.text(),'updated-version');
 }finally{await new Promise(r=>gateway.close(r));await rm(root,{recursive:true,force:true})}
});
