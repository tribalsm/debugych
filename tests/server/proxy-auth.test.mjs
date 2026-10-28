// Real TLS fixtures and the actual proxy. No provider requests or real credentials.
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn,spawnSync} from 'node:child_process';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import https from 'node:https';
import http from 'node:http';
import {once} from 'node:events';
const root=path.resolve(import.meta.dirname,'../..');
test('HTTPS credential pipe, protected origin and certificate validation',async()=>{
 const dir=await fs.mkdtemp(path.join(os.tmpdir(),'debugych-proxy-auth-'));const cert=path.join(process.env.DEBUGYCH_TEST_TLS_DIR||dir,'cert.pem'),key=path.join(process.env.DEBUGYCH_TEST_TLS_DIR||dir,'key.pem');
 if(!process.env.DEBUGYCH_TEST_TLS_DIR){const generated=spawnSync('openssl',['req','-x509','-newkey','rsa:2048','-nodes','-days','1','-keyout',key,'-out',cert,'-subj','/CN=localhost','-addext','subjectAltName=DNS:localhost'],{stdio:'ignore'});assert.equal(generated.status,0);}
 const calls=[];const api=https.createServer({key:await fs.readFile(key),cert:await fs.readFile(cert)},(req,res)=>{calls.push({authorization:req.headers.authorization,cookie:req.headers.cookie,url:req.url});res.setHeader('Content-Type','application/json');res.end('{"ok":true}')});api.listen(0,'127.0.0.1');await once(api,'listening');
 async function proxy(trust=true){const reserve=http.createServer();reserve.listen(0,'127.0.0.1');await once(reserve,'listening');const port=reserve.address().port;await new Promise(r=>reserve.close(r));const env={...process.env,DEBUGYCH_WEB_PORT:String(port),DEBUGYCH_API_URL:'https://localhost:'+api.address().port,DEBUGYCH_ALLOW_REMOTE_API:'1',DEBUGYCH_REMOTE_AUTH_STDIN:'1'};delete env.NODE_TLS_REJECT_UNAUTHORIZED;delete env.NODE_EXTRA_CA_CERTS;if(trust)env.NODE_EXTRA_CA_CERTS=cert;const child=spawn(process.execPath,[path.join(root,'scripts/serve-web.mjs')],{env,stdio:['pipe','pipe','pipe']});let output='';child.stdout.on('data',b=>output+=b);child.stderr.on('data',b=>output+=b);child.stdin.write(JSON.stringify({token:'A'.repeat(64)})+'\n');await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Proxy startup timeout')),7000);child.stdout.on('data',()=>{if(output.includes('Debugych production build:')){clearTimeout(timer);resolve()}});child.once('exit',()=>{clearTimeout(timer);reject(Error('Proxy startup failed'))})});return {child,url:'http://127.0.0.1:'+port,output:()=>output}}
 let p;
 try{
  p=await proxy();assert.equal((await fetch(p.url+'/api/projects',{method:'POST',headers:{Authorization:'Bearer untrusted',Cookie:'secret=do-not-forward','Content-Type':'application/json'},body:'{}'})).status,200);assert.equal(calls[0].authorization,'Bearer '+'A'.repeat(64));assert.equal(calls[0].cookie,undefined);assert.equal(calls[0].url,'/api/projects');
  for(const headers of [{Origin:'https://evil.invalid'},{'Sec-Fetch-Site':'cross-site'},{Host:'evil.invalid'}]){const status=await new Promise((resolve,reject)=>{const req=http.request(p.url+'/api/projects',{method:'POST',headers},res=>{res.resume();resolve(res.statusCode)});req.on('error',reject);req.end('{}')});assert.equal(status,403);}
  assert.equal(calls.length,1);assert.ok(!p.output().includes('A'.repeat(64)));const end=once(p.child,'exit');p.child.kill();await end;p=null;
  p=await proxy(false);assert.equal((await fetch(p.url+'/api/projects')).status,502);assert.equal(calls.length,1);assert.ok(!p.output().includes('A'.repeat(64)));
 }finally{if(p){const end=once(p.child,'exit');p.child.kill();await end}await new Promise(r=>api.close(r));await fs.rm(dir,{recursive:true,force:true})}
});
