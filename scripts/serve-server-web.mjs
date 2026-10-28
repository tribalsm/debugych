// Trusted browser session gateway. No model calls, persistent keys or third-party assets.
import http from 'node:http';
import {randomBytes,createHash} from 'node:crypto';
import {createReadStream} from 'node:fs';
import {stat,realpath} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {Transform} from 'node:stream';
import {readFileSync} from 'node:fs';

const cookieName='__Host-debugych';
const page=(account=false,message='')=>`<!doctype html><html lang="ru"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="dark"><title>Дебагыч - ${account?'сеанс':'вход'}</title><style>
*{box-sizing:border-box}body{margin:0;min-height:100svh;display:grid;place-items:center;padding:24px;background:#0b1018;color:#eef3ff;font:16px system-ui,sans-serif}main{width:min(460px,100%)}.brand{font-size:26px;font-weight:800}small,p{color:#b4c3d9;line-height:1.6}h1{font-size:32px;letter-spacing:-1px;margin:32px 0 14px}form{background:#141d2b;border:1px solid #2d3c52;border-radius:16px;padding:24px;margin-top:25px}label{display:block;margin-bottom:10px;font-weight:600}input,button{font:inherit;width:100%;padding:13px;border-radius:8px;border:1px solid #405578}input{background:#0b1320;color:#fff}button{margin-top:16px;background:#2860db;color:white;font-weight:600;cursor:pointer}a{color:#a9c8ff}:focus-visible{outline:3px solid #9dbbff;outline-offset:4px}.error{color:#ffb7bd}footer{margin-top:22px;font-size:13px;color:#8e9fb9}</style>
<main><div class="brand">дебагыч<span style="color:#80a7ff">.</span></div><small>AI QA Assistant</small><h1>${account?'Сеанс сервера':'Войдите в рабочую область'}</h1><p>${account?'Вы подключены к защищённому серверу.':'Тесты, доказательства ошибок и проверка исправлений - в одном месте. Для входа нужен ключ владельца сервера.'}</p>${message?'<p class="error" role="alert">'+message+'</p>':''}${account?'<p><a href="/">Вернуться в приложение</a></p><form method="post" action="/auth/logout"><button>Выйти из сеанса</button></form>':'<form method="post" action="/auth/login"><label for="token">Ключ доступа</label><input id="token" name="token" type="password" autocomplete="off" required minlength="43" maxlength="256" spellcheck="false"><button>Войти в Дебагыч</button></form><footer>Ключ не сохраняется в браузерном хранилище. Доступ работает через защищённую HttpOnly-сессию. Это рабочий веб-сервис, установка Desktop не требуется.</footer>'}</main></html>`;

export function createGateway({root,origin,upstream,demo=null,now=Date.now,idleMs=30*60*1000,maxAgeMs=8*60*60*1000}){
 const publicURL=new URL(origin),api=new URL(upstream);
 if(publicURL.protocol!=='https:'||publicURL.pathname!=='/'||publicURL.username||publicURL.password||publicURL.search||publicURL.hash)throw Error('HTTPS public origin required');
 if(api.protocol!=='http:'||!['api','127.0.0.1','localhost'].includes(api.hostname)||api.pathname!=='/'||api.username||api.password||api.search||api.hash)throw Error('Fixed private API required');
 root=path.resolve(root);
 if(demo&&(demo.version!==1||!demo.routes||!demo.projectId||!Array.isArray(demo.routes['/api/projects'])||demo.routes['/api/projects'].length!==1||demo.routes['/api/projects'][0].id!==demo.projectId))throw Error('Invalid public demo snapshot');
 const sessions=new Map(),attempts=new Map();
 const hash=value=>createHash('sha256').update(value).digest('hex');
 function sweep(){for(const [key,s]of sessions)if(s.until<=now()||s.active+idleMs<=now())sessions.delete(key);for(const [key,s]of attempts)if(s.until<=now())attempts.delete(key)}
 function session(req){sweep();const cookies=(req.headers.cookie||'').split(';').map(x=>x.trim()).filter(x=>x.startsWith(cookieName+'='));if(cookies.length!==1)return null;const value=cookies[0].slice(cookieName.length+1);if(!/^[a-f0-9]{64}$/.test(value))return null;const key=hash(value),s=sessions.get(key);if(s){s.active=now();return {key,...s}}return null}
 const clearCookie=res=>res.setHeader('Set-Cookie',`${cookieName}=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0`);
 const redirect=(res,to)=>{res.writeHead(303,{Location:to});res.end()};
 const html=(res,status,body)=>{res.writeHead(status,{'Content-Type':'text/html; charset=utf-8','Content-Security-Policy':"default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"});res.end(body)};
 const json=(res,status,detail)=>{res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify({detail}))};
 const sameOrigin=req=>req.headers.origin===publicURL.origin&&req.headers['sec-fetch-site']!=='cross-site';
 async function check(token){return new Promise(resolve=>{const request=http.request(new URL('/api/health',api),{headers:{Authorization:'Bearer '+token},timeout:5000},reply=>{const status=reply.statusCode;reply.resume();resolve(status)});request.on('timeout',()=>request.destroy());request.on('error',()=>resolve(502));request.end()})}
 async function login(req,res){
  if(!sameOrigin(req))return json(res,403,'Недопустимый источник запроса');
  if(!/^application\/x-www-form-urlencoded(?:;|$)/i.test(req.headers['content-type']||''))return json(res,415,'Ожидается форма входа');
  sweep();const ip=req.headers['x-real-ip']||req.socket.remoteAddress;let limit=attempts.get(ip);
  if(limit&&limit.count>=8)return html(res,429,page(false,'Слишком много попыток. Повторите через минуту.'));
  if(!limit){if(attempts.size>=1024)return json(res,429,'Повторите позднее');limit={count:0,until:now()+60000};attempts.set(ip,limit)}limit.count++;
  let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>2048)return json(res,413,'Форма слишком велика')}
  const values=new URLSearchParams(raw),token=values.get('token')||'';
  if(values.getAll('token').length!==1||!/^[-_A-Za-z0-9]{43,256}$/.test(token))return html(res,401,page(false,'Ключ доступа не принят.'));
  const status=await check(token);
  if(status!==200)return html(res,status===401||status===403?401:503,page(false,status===401||status===403?'Ключ доступа не принят.':'Сервер временно недоступен. Попробуйте позднее.'));
  if(sessions.size>=64)return html(res,503,page(false,'Лимит активных сеансов. Повторите позднее.'));
  const previous=session(req);if(previous)sessions.delete(previous.key);
  const value=randomBytes(32).toString('hex');sessions.set(hash(value),{token,until:now()+maxAgeMs,active:now()});
  res.setHeader('Set-Cookie',`${cookieName}=${value}; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=${Math.floor(maxAgeMs/1000)}`);redirect(res,'/');
 }
 function proxy(req,res,token,s){
  const headers={authorization:'Bearer '+token};for(const name of ['accept','content-type','content-length','content-encoding'])if(req.headers[name])headers[name]=req.headers[name];
  if(Number(headers['content-length']||0)>40*1024*1024)return json(res,413,'Файл превышает лимит');
  const target=new URL(req.url,api);if(target.origin!==api.origin)return json(res,400,'Недопустимый путь');
  let oversized=false;
  const request=http.request(target,{method:req.method,headers,timeout:100000},reply=>{
   if(s&&[401,403].includes(reply.statusCode)){sessions.delete(s.key);clearCookie(res)}
   const responseHeaders={};for(const name of ['content-type','content-length','content-disposition','content-encoding'])if(reply.headers[name])responseHeaders[name]=reply.headers[name];
   res.writeHead(reply.statusCode||502,responseHeaders);reply.pipe(res);
  });
  request.on('timeout',()=>request.destroy());request.on('error',()=>{if(!res.headersSent)json(res,oversized?413:502,oversized?'Файл превышает лимит':'Backend временно недоступен');else res.destroy()});
  let size=0;const bounded=new Transform({transform(chunk,_encoding,callback){size+=chunk.length;if(size>40*1024*1024){oversized=true;callback(Error('Body limit'))}else callback(null,chunk)}});
  bounded.on('error',()=>request.destroy());req.on('aborted',()=>request.destroy());res.on('close',()=>{if(!res.writableEnded)request.destroy()});req.pipe(bounded).pipe(request);
 }
 const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.webp':'image/webp','.glb':'model/gltf-binary','.woff2':'font/woff2','.mp4':'video/mp4'};
 const server=http.createServer(async(req,res)=>{
  res.setHeader('Cache-Control','no-store');res.setHeader('X-Content-Type-Options','nosniff');res.setHeader('X-Frame-Options','DENY');res.setHeader('Referrer-Policy','same-origin');
  try{
   if(req.headers.host!==publicURL.host)return json(res,403,'Недопустимый Host');
   const raw=req.url||'/';if(!raw.startsWith('/')||raw.startsWith('//')||raw.includes('\\'))return json(res,400,'Недопустимый путь');
   const pathname=decodeURIComponent(raw.split('?')[0]);if(pathname.includes('\0')||pathname.includes('\\')||pathname.split('/').some(p=>p==='..'||p.startsWith('.')))return json(res,400,'Недопустимый путь');
   const s=session(req);
   if(pathname==='/auth/login'){if(req.method==='GET'){if(demo&&!s&&!new URL(raw,publicURL).searchParams.has('owner'))return redirect(res,'/');return html(res,200,page())}if(req.method==='POST')return await login(req,res);return json(res,405,'Метод не разрешён')}
   if(pathname==='/auth/logout'){
    if(req.method!=='POST')return json(res,405,'Используйте выход из сеанса');
    if(!sameOrigin(req))return json(res,403,'Недопустимый источник запроса');if(s)sessions.delete(s.key);clearCookie(res);return redirect(res,'/auth/login');
   }
   const apiPath=/^\/api(?:\/|\?|$)/.test(raw)||/^\/(?:docs|openapi\.json)(?:\?|$)/.test(raw);
   if(apiPath){
    // Existing native clients keep their explicit Bearer flow. Browser cookies
    // are ambient credentials, so all their mutations require the exact Origin.
    const explicit=req.headers.authorization;
    if(explicit){if(!/^Bearer [-_A-Za-z0-9]{43,256}$/.test(explicit))return json(res,401,'Требуется действующий токен доступа');return proxy(req,res,explicit.slice(7),null)}
    if(!s&&demo){
     res.setHeader('X-Debugych-Public-Demo','1');
     if(!['GET','HEAD'].includes(req.method))return json(res,403,'Публичное демо доступно только для просмотра. Запуск AI и изменение проектов закрыты.');
     const u=new URL(raw,publicURL);u.searchParams.sort();const key=u.pathname+u.search;
     if(!Object.hasOwn(demo.routes,key))return json(res,404,'Данные не входят в публичный демо-проект');
     res.writeHead(200,{'Content-Type':'application/json; charset=utf-8'});return res.end(req.method==='HEAD'?undefined:JSON.stringify(demo.routes[key]));
    }
    if(!s)return json(res,401,'Войдите в Дебагыч');
    if(req.headers['sec-fetch-site']==='cross-site'||(!['GET','HEAD','OPTIONS'].includes(req.method)&&!sameOrigin(req)))return json(res,403,'Недопустимый источник запроса');
    return proxy(req,res,s.token,s);
   }
   if(!s&&!demo){if(['GET','HEAD'].includes(req.method))return redirect(res,'/auth/login');return json(res,401,'Войдите в Дебагыч')}
   if(pathname==='/auth/account'&&!s)return redirect(res,'/auth/login?owner=1');
   if(pathname==='/auth/account'){if(req.method!=='GET')return json(res,405,'Метод не разрешён');return html(res,200,page(true))}
   if(!['GET','HEAD'].includes(req.method))return json(res,405,'Метод не разрешён');
   let file=path.resolve(root,'.'+pathname);if(file!==root&&!file.startsWith(root+path.sep))return json(res,400,'Недопустимый путь');
   let info;try{info=await stat(file)}catch{}
   if(!info?.isFile()){if(path.extname(pathname))return json(res,404,'Файл не найден');file=path.join(root,'index.html');info=await stat(file)}
   const actual=await realpath(file);if(!actual.startsWith(root+path.sep))return json(res,400,'Недопустимый путь');
   res.writeHead(200,{'Content-Type':types[path.extname(file)]||'application/octet-stream','Content-Length':info.size});
   if(req.method==='HEAD')res.end();else createReadStream(file).on('error',()=>res.destroy()).pipe(res);
  }catch{if(!res.headersSent)json(res,400,'Не удалось обработать запрос');else res.destroy()}
 });
 server.headersTimeout=15000;server.requestTimeout=120000;
 server.on('close',()=>{sessions.clear();attempts.clear()});return server;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
 const demo=process.env.PUBLIC_DEMO_FILE?JSON.parse(readFileSync(process.env.PUBLIC_DEMO_FILE,'utf8')):null;
 const server=createGateway({root:process.env.WEB_ROOT||'/app/public',origin:process.env.PUBLIC_ORIGIN,upstream:process.env.API_UPSTREAM||'http://api:8000',demo});
 server.listen(Number(process.env.PORT||8080),'0.0.0.0',()=>console.log('Debugych web gateway ready'));
 for(const signal of ['SIGTERM','SIGINT'])process.on(signal,()=>{server.close();server.closeIdleConnections();setTimeout(()=>process.exit(0),5000).unref()});
}
