import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import {fileURLToPath} from 'node:url';
import {options,backendStatus} from '../../scripts/start-local.mjs';

test('launcher accepts loopback forwarding and rejects exposed or credential-bearing API URLs',()=>{
 assert.equal(options(['--api-url','http://127.0.0.1:18000','--port','18888']).port,18888);
 for(const api of ['https://127.0.0.1','http://example.com','http://key@localhost','http://localhost/path','http://localhost/#key'])assert.throws(()=>options(['--api-url',api]));
 assert.throws(()=>options(['--port','800']));assert.throws(()=>options(['--api-url']));assert.throws(()=>options(['--project','bad;echo']));
});
test('backend readiness requires a real execution contract but does not require an AI key',async()=>{
 let health={status:'ok',execution:'trusted-demo-only',sandbox_available:false,ai_available:false};
 const api=http.createServer((req,res)=>{res.setHeader('Content-Type','application/json');res.end(JSON.stringify(health))});api.listen(0,'127.0.0.1');await once(api,'listening');
 try{const url='http://127.0.0.1:'+api.address().port;assert.equal((await backendStatus(url)).ready,false);health={...health,execution:'gvisor-python',sandbox_available:true};const s=await backendStatus(url);assert.equal(s.ready,true);assert.equal(s.aiAvailable,false)}finally{await new Promise(r=>api.close(r))}
});
test('launcher reuses fixture health, proxies GET only, and cleans up its own web server on shutdown',async()=>{
 const paths=[];const api=http.createServer((req,res)=>{paths.push(req.method+' '+req.url);res.setHeader('Content-Type','application/json');res.end(JSON.stringify(req.url==='/api/health'?{status:'ok',execution:'gvisor-python',sandbox_available:true,ai_available:false}:{fixture:true}))});api.listen(0,'127.0.0.1');await once(api,'listening');
 const reserve=http.createServer();reserve.listen(0,'127.0.0.1');await once(reserve,'listening');const port=reserve.address().port;await new Promise(r=>reserve.close(r));
 const launcher=fileURLToPath(new URL('../../scripts/start-local.mjs',import.meta.url));const c=spawn(process.execPath,[launcher,'--reuse-backend','--port',String(port),'--api-url','http://127.0.0.1:'+api.address().port],{stdio:['ignore','pipe','pipe']});let output='';c.stdout.on('data',b=>output+=b);c.stderr.on('data',b=>output+=b);
 try{
  await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(output)),10000);const onData=()=>{if(output.includes('Debugych production build:')){clearTimeout(timer);c.stdout.off('data',onData);resolve()}};c.stdout.on('data',onData);c.once('exit',code=>{clearTimeout(timer);reject(Error('early exit '+code+': '+output))})});
  const page=await fetch('http://127.0.0.1:'+port);assert.match(await page.text(),/Дебагыч/);assert.equal((await(await fetch('http://127.0.0.1:'+port+'/api/projects')).json()).fixture,true);
  assert.ok(paths.every(p=>p.startsWith('GET ')));assert.match(output,/AI is not configured/);
 }finally{
  const ended=once(c,'exit');c.kill('SIGTERM');await ended;await new Promise(r=>api.close(r));
 }
 // Unix handles SIGTERM in the launcher and waits for its own child. Windows
 // TerminateProcess does not have POSIX signal semantics; test that path on Unix.
 if(process.platform!=='win32')await assert.rejects(fetch('http://127.0.0.1:'+port));
});
