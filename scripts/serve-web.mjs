// Local production frontend and same-origin proxy, using only Node built-ins.
import http from 'node:http';
import https from 'node:https';
import net from 'node:net';
import {createReadStream} from 'node:fs';
import {stat} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(fileURLToPath(new URL('../apps/web/dist/',import.meta.url)));
const port=Number(process.env.DEBUGYCH_WEB_PORT||8798),upstream=new URL(process.env.DEBUGYCH_API_URL||'http://127.0.0.1:8000');
const localHTTP=upstream.protocol==='http:'&&['127.0.0.1','localhost','[::1]'].includes(upstream.hostname);
const approvedHTTPS=upstream.protocol==='https:'&&process.env.DEBUGYCH_ALLOW_REMOTE_API==='1';
const remoteUI=process.env.DEBUGYCH_UI_SOURCE==='remote';
if(remoteUI&&!approvedHTTPS)throw Error('Server-rendered workspace requires an approved HTTPS origin');
const routeIP=process.env.DEBUGYCH_API_CONNECT_IP||'';
const octets=routeIP.split('.').map(Number);
if(routeIP&&(!approvedHTTPS||net.isIP(routeIP)!==4||!(octets[0]===10||(octets[0]===172&&octets[1]>=16&&octets[1]<=31)||(octets[0]===192&&octets[1]===168))))throw Error('An explicit private VPN IPv4 route requires HTTPS');
// Lookup override preserves the approved URL, Host, SNI and normal certificate checks.
const transport=routeIP?{servername:upstream.hostname,lookup:(hostname,options,callback)=>{if(hostname!==upstream.hostname)return callback(Error('Unexpected route hostname'));if(options?.all)callback(null,[{address:routeIP,family:4}]);else callback(null,routeIP,4)}}:{};
let serverToken='',serverSession='';
if(process.env.DEBUGYCH_REMOTE_AUTH_STDIN==='1'){
 if(!approvedHTTPS)throw Error('Credentials require an approved HTTPS server');
 const credential=await new Promise((resolve,reject)=>{let raw='';const timer=setTimeout(()=>{cleanup();reject(Error('Credential pipe timeout'))},5000);const cleanup=()=>{clearTimeout(timer);process.stdin.off('data',read);process.stdin.pause()};const read=chunk=>{raw+=chunk;if(raw.length>1024){cleanup();reject(Error('Invalid credential envelope'));return}if(raw.includes('\n')){cleanup();try{const value=JSON.parse(raw.split('\n')[0]);if(!value||Object.keys(value).length!==1)throw Error();if(typeof value.token==='string'&&/^[A-Za-z0-9_-]{43,256}$/.test(value.token))resolve(value);else if(typeof value.session==='string'&&/^[a-f0-9]{64}$/.test(value.session))resolve(value);else throw Error()}catch{reject(Error('Invalid credential envelope'))}}};process.stdin.setEncoding('utf8');process.stdin.on('data',read);process.stdin.resume()});
 serverToken=credential.token||'';serverSession=credential.session||'';
}
if(!Number.isInteger(port)||port<1024||port>65535||!(localHTTP||approvedHTTPS)||upstream.username||upstream.password||upstream.pathname!=='/'||upstream.search||upstream.hash)throw Error('Use a loopback HTTP API origin or an explicitly configured HTTPS server and port 1024..65535');
if(!remoteUI)await stat(path.join(root,'index.html'));
const ownOrigin=`http://127.0.0.1:${port}`;
let boundFrame='';
function workspaceLink(){return ownOrigin+'/?desktop_backend='+encodeURIComponent(upstream.origin)+(boundFrame?'&desktop_session='+encodeURIComponent(boundFrame):'')}
function replyUnavailable(res){res.writeHead(502,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Нет связи с сервером</title><body style="background:#101722;color:#e5edf8;font:16px system-ui;padding:40px"><h1>Интерфейс сервера временно недоступен</h1><p>Проверьте соединение и повторите загрузку. Локальная копия не подставляется вместо сайта.</p><a style="color:#a9c8ff" href="'+workspaceLink()+'">Повторить загрузку</a></body></html>')}
function responseHeaders(reply){
 const headers={...reply.headers};delete headers['set-cookie'];
 if(remoteUI){
  delete headers['x-frame-options'];
  if(process.env.DEBUGYCH_DESKTOP_EMBED==='1'){const directives=String(headers['content-security-policy']||'').split(';').map(x=>x.trim()).filter(x=>x&&!/^frame-ancestors\b/i.test(x));directives.push('frame-ancestors http://tauri.localhost tauri://localhost');headers['content-security-policy']=directives.join('; ')}
  if(headers.location){const target=new URL(headers.location,upstream);if(target.origin!==upstream.origin)throw Error('Foreign redirect refused');headers.location=ownOrigin+target.pathname+target.search+target.hash;}
  if(String(headers['content-type']||'').startsWith('text/html'))headers['cache-control']='no-store';
 }
 return headers;
}
const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json; charset=utf-8','.png':'image/png','.jpg':'image/jpeg','.svg':'image/svg+xml','.glb':'model/gltf-binary','.woff2':'font/woff2','.mp4':'video/mp4'};
const server=http.createServer(async(req,res)=>{
 res.setHeader('X-Content-Type-Options','nosniff');if(process.env.DEBUGYCH_DESKTOP_EMBED==='1')res.setHeader('Content-Security-Policy',"frame-ancestors http://tauri.localhost tauri://localhost");else res.setHeader('X-Frame-Options','DENY');
 const raw=req.url||'/';
 const isAPI=/^\/api(?:\/|\?|$)/.test(raw)||/^\/(?:docs|openapi\.json)(?:\?|$)/.test(raw);
 if(remoteUI){
  if(req.headers.host!==`127.0.0.1:${port}`||(req.headers.origin&&req.headers.origin!==ownOrigin)){res.writeHead(403);res.end('Untrusted workspace origin');return;}
  try{const p=decodeURIComponent(raw.split('?')[0]);if(!raw.startsWith('/')||raw.startsWith('//')||p.includes('\\')||p.includes('\0')||p.split('/').some(s=>s==='..'||s.startsWith('.')))throw Error();const value=new URL(raw,ownOrigin).searchParams.get('desktop_session');if(!boundFrame&&value&&/^[a-f0-9-]{36}$/i.test(value))boundFrame=value;}catch{res.writeHead(400);res.end('Invalid workspace path');return;}
  // Native owns login/logout, cookie storage and the pet session. Never let a
  // web form silently replace only one half of that shared identity.
  if(/^\/auth(?:\/|\?|$)/.test(raw)){
   res.writeHead(409,{'Content-Type':'text/html; charset=utf-8','Cache-Control':'no-store'});res.end('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Аккаунт Desktop</title><body style="background:#101722;color:#e5edf8;font:16px system-ui;padding:40px"><h1>Аккаунт Desktop</h1><p>Для входа и выхода используйте меню «Подключение / аккаунт». Регистрация и смена пароля доступны на сайте в браузере.</p><a style="color:#a9c8ff" href="'+workspaceLink()+'">Вернуться к рабочей области</a></body></html>');return;
  }
  if(!isAPI&&!['GET','HEAD'].includes(req.method||'')){res.writeHead(405);res.end('Workspace navigation is read-only');return;}
 }
 if(isAPI||remoteUI){
  // Stop browser CSRF and DNS rebinding against this credential-bearing loopback proxy.
  if(req.headers.host!==`127.0.0.1:${port}`||(req.headers.origin&&req.headers.origin!==ownOrigin)||(isAPI&&req.headers['sec-fetch-site']==='cross-site')){
   res.writeHead(403,{'Content-Type':'application/json'});res.end(JSON.stringify({detail:'Untrusted local proxy origin'}));return;
  }
  const headers={...req.headers,host:upstream.host,connection:'close'};delete headers.authorization;delete headers.cookie;
  if(serverToken)headers.authorization='Bearer '+serverToken;
  if(serverSession){headers.cookie='__Host-debugych='+serverSession;headers.origin=upstream.origin;headers['x-debugych-require-session']='1';}
  const target=new URL(raw,upstream);if(target.origin!==upstream.origin){res.writeHead(400);res.end('Invalid upstream origin');return;}
  const proxy=(upstream.protocol==='https:'?https:http).request(target,{...transport,method:req.method,headers,timeout:90000},reply=>{try{const safe=responseHeaders(reply);res.writeHead(reply.statusCode||502,safe);reply.pipe(res)}catch{reply.resume();if(!res.headersSent)res.writeHead(502);res.end('Unsafe upstream response refused')}});
  proxy.on('timeout',()=>proxy.destroy());proxy.on('error',()=>{if(res.headersSent){res.destroy();return;}if(remoteUI&&!isAPI){replyUnavailable(res);return;}res.writeHead(502,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail:'Сервер недоступен. Проверьте соединение.'}))});
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
