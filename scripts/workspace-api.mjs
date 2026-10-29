import http from 'node:http';
import {AccountError} from './web-accounts.mjs';
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
export function workspaceAPI({api,store,proxy,tokenFor,now=Date.now}){
 const uploads=new Set(),creating=new Set(),runChecks=new Set(),executions=new Map();let cleaning=false;
 function releaseProject(pid){for(const [scope,entry]of executions)if(entry.project_id===pid)executions.delete(scope)}
 async function call(path,token,{method='GET',body}={}){
  return new Promise((resolve,reject)=>{
   const headers={Authorization:'Bearer '+token};if(body){headers['Content-Type']='application/json';headers['Content-Length']=Buffer.byteLength(body)}
   const request=http.request(new URL(path,api),{method,headers,timeout:10000},reply=>{let raw='';reply.setEncoding('utf8');reply.on('data',chunk=>{raw+=chunk;if(Buffer.byteLength(raw)>4*1024*1024)request.destroy(Error('Response limit'))});reply.on('end',()=>{let value;try{value=JSON.parse(raw)}catch{value={detail:'Backend вернул некорректный ответ'}}resolve({status:reply.statusCode,value})})});
   request.on('timeout',()=>request.destroy());request.on('error',()=>reject(new AccountError(502,'Backend временно недоступен')));request.end(body);
  });
 }
 function reply(res,status,value,s){res.setHeader('X-Debugych-Workspace',s.guest?'guest':'account');res.writeHead(status,{'Content-Type':'application/json; charset=utf-8'});res.end(JSON.stringify(value))}
 async function jsonBody(req){let raw='';for await(const chunk of req){raw+=chunk;if(Buffer.byteLength(raw)>16384)throw new AccountError(413,'Запрос слишком велик')}try{return JSON.parse(raw||'{}')}catch{throw new AccountError(400,'Некорректный JSON')}}
 async function ensure(s,id){if(!uuid.test(id||'')||!store.owns(s,id))throw new AccountError(404,'Проект или результат не найден в вашей истории')}
 async function capacity(token){const result=await call('/api/storage-usage',token);if(result.status!==200||!Number.isFinite(result.value.estimated_bytes))throw new AccountError(503,'Не удалось проверить свободное место');if(result.value.estimated_bytes>1792*1024*1024)throw new AccountError(507,'Хранилище заполнено. Удалите ненужные проекты или обратитесь к администратору.')}
 async function clean(token){
  if(cleaning)return;cleaning=true;
  try{for(const {project_id}of store.expired().slice(0,5)){const result=await call('/api/projects/'+project_id,token,{method:'DELETE'});if([200,404].includes(result.status)){store.remove(project_id);releaseProject(project_id)}}store.prune()}finally{cleaning=false}
 }
 const handle=async function(req,res,s,pathname){
  const token=tokenFor(s),u=new URL(req.url,'http://workspace'),method=req.method;
  // URLSearchParams.get uses the first value; FastAPI can use the last.
  // Reject duplicates before forwarding to prevent ownership-check ambiguity.
  if([...u.searchParams.keys()].some(key=>u.searchParams.getAll(key).length!==1))throw new AccountError(400,'Повторяющиеся параметры запроса недопустимы');
  void clean(token).catch(()=>{});
  const upstream=async(path,options)=>{const result=await call(path,token,options);reply(res,result.status,result.value,s);return result};
  if(pathname==='/api/health'||pathname==='/api/ai/status'){
   if(method!=='GET')throw new AccountError(405,'Метод не разрешён');const result=await call(pathname,token);
   if(result.status===200){Object.assign(result.value,{workspace_mode:s.guest?'guest':'account',guest_history_days:30,can_import_tests:true});if(s.guest)Object.assign(result.value,{ai_available:false,configured:false,ai_status:'guest-uploaded-tests-only',status:pathname.endsWith('/status')?'guest-uploaded-tests-only':result.value.status})}
   return reply(res,result.status,result.value,s);
  }
  if(pathname==='/api/projects'&&method==='GET'){
   const result=await call(pathname,token);if(result.status===200)result.value=result.value.filter(p=>store.owns(s,p.id));return reply(res,result.status,result.value,s);
  }
  if((pathname==='/api/projects'||pathname==='/api/demo')&&method==='POST'){
   if(creating.has(s.id))throw new AccountError(429,'Создание проекта ещё выполняется');creating.add(s.id);
   try{store.assertCreate(s);await capacity(token);const body=JSON.stringify(await jsonBody(req)),result=await call(pathname,token,{method,body});
    if(result.status===201&&uuid.test(result.value?.id||''))store.attach(s,result.value.id);
    return reply(res,result.status,result.value,s);
   }finally{creating.delete(s.id)}
  }
  if(pathname==='/api/bugs'&&method==='GET'){
   if(u.searchParams.has('project_id'))await ensure(s,u.searchParams.get('project_id'));
   const result=await call(req.url,token);if(result.status===200)result.value=result.value.filter(b=>store.owns(s,b.project_id));return reply(res,result.status,result.value,s);
  }
  if(pathname==='/api/demo-web'&&method==='GET')return proxy(req,res,token,s);
  if(!s.guest&&['/docs','/openapi.json'].includes(pathname)&&method==='GET')return proxy(req,res,token,s);
  let pid,record,operation='',match=pathname.match(/^\/api\/projects\/([^/]+)(?:\/(files|requirements|test-cases|runs|fixes|ai-context|ai-statistics|analyze|autonomous|accept-ai-draft|source-archive|import-tests))?$/);
  if(match){pid=match[1];operation=match[2]||'';await ensure(s,pid)}
  else if(pathname==='/api/exports'&&method==='GET'){pid=u.searchParams.get('project_id');await ensure(s,pid)}
  else if((match=pathname.match(/^\/api\/(bugs|runs|test-cases)\/([^/]+)(?:\/(coverage|artifacts|confirm-proof|propose-fix|verify-fix|apply-fix)(?:\/([a-f0-9-]+))?)?$/))){
   if(!uuid.test(match[2]))throw new AccountError(404,'Результат не найден');
   if(match[1]==='test-cases'){
    if(!['GET','PATCH'].includes(method)||match[3])throw new AccountError(405,'Метод не разрешён');
    const result=await call('/api/test-cases/'+match[2],token);if(result.status!==200)throw new AccountError(404,'Тест не найден');pid=result.value.project_id;await ensure(s,pid);
   }else{
    const result=await call('/api/'+match[1]+'/'+match[2],token);if(result.status!==200)throw new AccountError(404,'Результат не найден');record=result.value;pid=record.project_id;await ensure(s,pid);
   }
   operation=match[3]||'';
   if(match[4]&&!uuid.test(match[4]))throw new AccountError(404,'Артефакт не найден');
  }else if(['/api/companion/context','/api/companion/ask'].includes(pathname)&&method==='POST'){
   if(s.guest)throw new AccountError(403,'Войдите в аккаунт для AI-чата. Гостевой запуск загруженных тестов доступен без LLM.');
   const body=await jsonBody(req);await ensure(s,body.project_id);return upstream(pathname,{method,body:JSON.stringify(body)});
  }else throw new AccountError(404,'Раздел недоступен в рабочей области');
  if(s.guest&&['analyze','autonomous','ai-context','accept-ai-draft','propose-fix'].includes(operation)){
   const project=await call('/api/projects/'+pid,token);
   if(!(operation==='analyze'&&project.status===200&&project.value.demo))throw new AccountError(403,'Для AI-генерации войдите в аккаунт. В гостевом режиме можно загрузить собственные тесты или запустить подготовленное демо.');
  }
  if(!['GET','HEAD','POST','PATCH','DELETE'].includes(method))throw new AccountError(405,'Метод не разрешён');
  if(method==='DELETE'){
   if(operation||!pathname.startsWith('/api/projects/'))throw new AccountError(405,'Удаление недоступно');
   const result=await call(pathname,token,{method});if([200,404].includes(result.status)){store.remove(pid);releaseProject(pid)}return reply(res,result.status,result.value,s);
  }
  if(operation==='files'&&method==='POST'){
   if(uploads.has(s.id)||uploads.size>=2)throw new AccountError(429,'Другая загрузка ещё выполняется. Повторите после её завершения.');store.assertUpload(s,uploads.size*30*1024*1024);uploads.add(s.id);
   try{await capacity(token)}catch(e){uploads.delete(s.id);throw e}
   const prior=store.projects(s).find(p=>p.project_id===pid);if(prior)store.size(pid,prior.bytes+30*1024*1024);
   return proxy(req,res,token,s,{after:async()=>{try{const result=await call(`/api/projects/${pid}/files`,token);if(result.status===200)store.size(pid,result.value.reduce((n,f)=>n+(f.size||0),0))}finally{uploads.delete(s.id)}}});
  }
  if(operation==='files'&&method==='GET'){
   const result=await call(pathname,token);if(result.status===200)store.size(pid,result.value.reduce((n,f)=>n+(f.size||0),0));return reply(res,result.status,result.value,s);
  }
  if(method==='POST'&&['runs','confirm-proof','verify-fix','analyze','autonomous','propose-fix'].includes(operation)){
   if(runChecks.has(s.id))throw new AccountError(429,'Предыдущий запуск ещё выполняется');runChecks.add(s.id);
   try{
   await capacity(token);
   for(const [scope,entry]of executions){if(entry.until<=now()){executions.delete(scope);continue}if(entry.id){const state=await call('/api/runs/'+entry.id,token);if(state.status===200&&['completed','failed','cancelled','manual_review_required'].includes(state.value.status))executions.delete(scope)}}
   if(executions.size+runChecks.size>4)throw new AccountError(429,'Сервер занят другими проверками. Повторите позже.');
   const prior=executions.get(s.id);if(prior&&prior.until>now()){
    if(!prior.id)throw new AccountError(429,'Предыдущий запуск ещё выполняется');const state=await call('/api/runs/'+prior.id,token);
    if(state.status!==200||!['completed','failed','cancelled','manual_review_required'].includes(state.value.status))throw new AccountError(429,'Предыдущий запуск ещё выполняется');
   }
   store.reserveRun(s,req);if(!['owner','admin'].includes(s.role))store.consume('global','workspace-run',40);executions.set(s.id,{project_id:pid,until:now()+600000});
   return proxy(req,res,token,s,{capture:true,after:async value=>{if(value?.id)executions.set(s.id,{id:value.id,project_id:pid,until:now()+600000});else executions.delete(s.id)}});
   }finally{runChecks.delete(s.id)}
  }
  return proxy(req,res,token,s);
 };
 handle.sweep=()=>clean(tokenFor({role:'maintenance'}));
 return handle;
}
