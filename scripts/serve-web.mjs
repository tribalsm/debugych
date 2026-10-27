// Local production frontend and same-origin proxy, using only Node built-ins.
import http from 'node:http';
import https from 'node:https';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(fileURLToPath(new URL('../apps/web/dist/',import.meta.url)));
const port=Number(process.env.DEBUGYCH_WEB_PORT||8798),upstream=new URL(process.env.DEBUGYCH_API_URL||'http://127.0.0.1:8000');
const localHTTP=upstream.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(upstream.hostname);
const approvedHTTPS=upstream.protocol==='https:'&&process.env.DEBUGYCH_ALLOW_REMOTE_API==='1';
if(!Number.isInteger(port)||port<1024||port>65535||!(localHTTP||approvedHTTPS)||upstream.username||upstream.password||upstream.pathname!=='/'||upstream.search||upstream.hash)throw Error('Use a loopback HTTP API origin or an explicitly configured HTTPS server and port 1024..65535');
await stat(path.join(root,'index.html'));
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml','.glb':'model/gltf-binary','.woff2':'font/woff2','.mp4':'video/mp4'};
const server=http.createServer(async(req,res)=>{
 res.setHeader('X-Content-Type-Options','nosniff');if(process.env.DEBUGYCH_DESKTOP_EMBED==='1')res.setHeader('Content-Security-Policy',"frame-ancestors http://tauri.localhost tauri://localhost");else res.setHeader('X-Frame-Options','DENY');
 const raw=req.url||'/';
 if(/^\/api(?:\/|\?|$)/.test(raw)||/^\/(?:docs|openapi\.json)(?:\?|$)/.test(raw)){
  const proxy=(upstream.protocol==='https:'?https:http).request(new URL(raw,upstream),{method:req.method,headers:{...req.headers,host:upstream.host,connection:'close'},timeout:90000},reply=>{res.writeHead(reply.statusCode||502,reply.headers);reply.pipe(res)});
  proxy.on('timeout',()=>proxy.destroy());proxy.on('error',()=>{if(!res.headersSent)res.writeHead(502,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail:'Backend недоступен. Проверьте локальный запуск API.'}))});
  req.on('aborted',()=>proxy.destroy());res.on('close',()=>{if(!res.writableEnded)proxy.destroy()});req.pipe(proxy);return;
 }
 if(!['GET','HEAD'].includes(req.method||'')){res.writeHead(405);res.end();return;}
 try{
  const pathname=decodeURIComponent(raw.split('?')[0]);
  if(pathname.includes('\0')||pathname.includes('\\')||pathname.split('/').some(p=>p==='..'||p.startsWith('.'))){res.writeHead(400);res.end('Invalid path');return;}
  let target=path.resolve(root,'.'+pathname);if(!target.startsWith(root+path.sep)&&target!==root){res.writeHead(400);res.end();return;}
  let info;try{info=await stat(target)}catch{/* Navigation falls back to the SPA only without a file extension. */}
  if(!info?.isFile()){if(path.extname(pathname)){res.writeHead(404);res.end('Not found');return;}target=path.join(root,'index.html');info=await stat(target);}
  res.writeHead(200,{'Content-Type':types[path.extname(target)]||'application/octet-stream','Content-Length':info.size,'Cache-Control':path.extname(target)==='.html'?'no-store':'public, max-age=3600'});
  if(req.method==='HEAD')res.end();else createReadStream(target).on('error',()=>res.destroy()).pipe(res);
 }catch{res.writeHead(400);res.end('Invalid request');}
});
server.listen(port,'127.0.0.1',()=>console.log(`Debugych production build: http://127.0.0.1:${port}/ | API: ${upstream.origin}`));
server.on('error',e=>{console.error(e.code==='EADDRINUSE'?'Port is occupied. Stop only your previous preview or set DEBUGYCH_WEB_PORT.':e.message);process.exitCode=1;});
