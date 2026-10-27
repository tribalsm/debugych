import{baseUrl,uuid,type CompanionConfig,type Project,type Context,type Run,type Bug,type Fix,type Connection,type TestCase,type Requirement}from'./contracts.js';
export class ApiError extends Error {constructor(readonly status:number,message:string){super(message);}}
export interface ApiTransport {get:(path:string,signal:AbortSignal)=>Promise<unknown>}
export interface BackendUpdate {connection:Connection;message:string;projects?:Project[];context?:Context;health?:Record<string,unknown>;lastConfirmedAt?:number}
export interface AdapterOptions {transport:ApiTransport;publish:(u:BackendUpdate)=>void;schedule?:(fn:()=>void,ms:number)=>unknown;cancel?:(id:unknown)=>void;now?:()=>number;isInspecting?:()=>boolean;loadChatContext?:()=>boolean}
const signature=(rows:Run[])=>JSON.stringify(rows.map(r=>[r.id,r.status,r.stage,r.parent_workflow_id,r.verified,r.fix_id]));
function records<T extends {id:string}>(v:unknown):T[]{if(!Array.isArray(v)||v.length>10000||v.some(r=>!r||!uuid(r.id)))throw new ApiError(422,'Несовместимый формат API');return v as T[];}
/** One poll at a time, bounded backoff, abort on scope change. All requests are GET. */
export class DesktopPetBackendAdapter {
 private timer:unknown=null;private abort:AbortController|null=null;private generation=0;private failures=0;private connected=false;private disposed=false;private config:CompanionConfig|null=null;
 private schedule:(f:()=>void,ms:number)=>unknown;private cancel:(id:unknown)=>void;private now:()=>number;
 constructor(private options:AdapterOptions){this.schedule=options.schedule??((f,ms)=>setTimeout(f,ms));this.cancel=options.cancel??(id=>clearTimeout(id as number));this.now=options.now??Date.now;}
 configure(config:CompanionConfig){baseUrl(config.backendUrl);this.stop();this.config={...config};this.failures=0;this.connected=false;if(config.enabled&&!this.disposed)void this.poll(this.generation);}
 private current(n:number){return!this.disposed&&n===this.generation&&!!this.config?.enabled;}
 private async poll(n:number){
  if(!this.current(n))return;const config=this.config!;this.abort=new AbortController();const signal=this.abort.signal;let delay=10000;
  if(!this.connected&&this.failures===0)this.options.publish({connection:'connecting',message:'Подключение к backend'});
  try{
   const health=await this.options.transport.get('/api/health',signal) as Record<string,unknown>;if(!health||health.status!=='ok'||!['trusted-demo-only','gvisor-python'].includes(String(health.execution)))throw new ApiError(422,'Сервер не соответствует API Дебагыча');
   const projects=records<Project>(await this.options.transport.get('/api/projects',signal));if(projects.some(p=>typeof p.name!=='string'||typeof p.demo!=='boolean'))throw new ApiError(422,'Несовместимый список проектов');
   if(!this.current(n))return;
   const project=projects.find(p=>p.id===config.projectId);let context:Context|undefined;
   if(project){
    const path='/api/projects/'+project.id;const runs=records<Run>(await this.options.transport.get(path+'/runs',signal));
    const bugs=records<Bug>(await this.options.transport.get('/api/bugs?project_id='+project.id,signal));
    const fixes=records<Fix>(await this.options.transport.get(path+'/fixes',signal));
    let metadata:{tests:TestCase[];requirements:Requirement[]}|undefined;
    if(this.options.loadChatContext?.()){const [tests,requirements]=await Promise.all([this.options.transport.get(path+'/test-cases',signal),this.options.transport.get(path+'/requirements',signal)]);if(!this.current(n))return;metadata={tests:records<TestCase>(tests),requirements:records<Requirement>(requirements)};}
    const after=records<Run>(await this.options.transport.get(path+'/runs',signal));
    if(signature(runs)!==signature(after)){delay=2000;this.connected=true;this.failures=0;if(this.current(n))this.options.publish({connection:'connected',message:'Задание изменилось, уточняю согласованное состояние',projects,health});return;}
    if([...runs,...bugs,...fixes,...metadata?.tests??[],...metadata?.requirements??[]].some(r=>r.project_id!==project.id))throw new ApiError(422,'API вернул данные другого проекта');
    context={project,runs,bugs,fixes,selectedRunId:config.runId||undefined,tests:metadata?.tests,requirements:metadata?.requirements};
    const working=runs.some(r=>['queued','analyzing','generating','running'].includes(r.status));
    delay=this.options.isInspecting?.()?(working?1500:3000):(working?3000:10000);
   }
   if(!this.current(n))return;this.failures=0;this.connected=true;this.options.publish({connection:'connected',message:config.projectId&&!project?'Выбранный проект отсутствует':project?'Подключено':'Выберите проект',projects,context,health,lastConfirmedAt:this.now()});
  }catch(error){if(!this.current(n)||signal.aborted)return;this.connected=false;this.failures++;delay=Math.min(60000,5000*2**Math.min(this.failures-1,4));const e=error as Error;
   const code=error instanceof ApiError?error.status:0;this.options.publish({connection:code===401||code===403?'authorization_required':code>=500?'server_error':code===422?'incompatible':'offline',message:code===401||code===403?'Требуется авторизация в существующей системе':code>=500?'Ошибка сервера. Результат не подтверждён':code===422?e.message:'Нет подключения к backend'});
  }finally{if(this.current(n)){this.abort=null;this.timer=this.schedule(()=>{this.timer=null;void this.poll(n);},delay);}}
 }
 stop(){this.generation++;this.abort?.abort();this.abort=null;if(this.timer!==null)this.cancel(this.timer);this.timer=null;}
 dispose(){this.disposed=true;this.stop();}
}
