// Free, cross-platform smoke of the packaged production server. No AI requests.
import {spawn} from 'node:child_process';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import assert from 'node:assert/strict';
const port=Number(process.env.DEBUGYCH_CHECK_PORT||18798);
const child=spawn(process.execPath,[fileURLToPath(new URL('./serve-web.mjs',import.meta.url))],{env:{...process.env,DEBUGYCH_WEB_PORT:String(port)},stdio:['ignore','pipe','pipe']});
const get=path=>new Promise((resolve,reject)=>{const req=http.get({hostname:'127.0.0.1',port,path},r=>{let body='';r.setEncoding('utf8');r.on('data',c=>body+=c);r.on('end',()=>resolve({status:r.statusCode,type:r.headers['content-type'],body}))});req.on('error',reject);req.setTimeout(5000,()=>req.destroy(Error('HTTP timeout')))});
try{
 await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Server startup timed out')),10000);child.stdout.once('data',()=>{clearTimeout(timer);resolve()});child.once('error',reject);child.once('exit',code=>{clearTimeout(timer);reject(Error('Server exited: '+code))});child.stderr.on('data',c=>process.stderr.write(c))});
 const index=await get('/');assert.equal(index.status,200);assert.match(index.body,/Дебагыч/);
 const asset=index.body.match(/src="([^\"]+\.js)"/)[1];const js=await get(asset);assert.equal(js.status,200);assert.match(js.type,/javascript/);
 assert.equal((await get('/favicon.svg')).status,200);
 assert.equal((await get('/companion/manifest.json')).status,200);
 assert.equal((await get('/.env')).status,400);
 assert.equal((await get('/%2e%2e/.env')).status,400);
 console.log(JSON.stringify({platform:process.platform,arch:process.arch,node:process.version,productionServer:'PASS',checks:6}));
}finally{
 if(child.exitCode===null){const ended=new Promise(resolve=>child.once('exit',resolve));child.kill();await ended}
}
