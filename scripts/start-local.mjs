// macOS / Linux launcher. Reuses the same backend, Compose and production web server.
import {spawn,spawnSync} from 'node:child_process';
import {access,copyFile,constants} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
import net from 'node:net';
const root=fileURLToPath(new URL('../',import.meta.url));

export function options(args){
 const o={port:8798,api:'http://127.0.0.1:8000',project:'debugych',envFile:path.join(root,'.env'),doctor:false,build:false,startBackend:false,open:false};
 for(let i=0;i<args.length;i++){
  const a=args[i];
  if(['--doctor','--build','--start-backend','--open'].includes(a))o[{'--doctor':'doctor','--build':'build','--start-backend':'startBackend','--open':'open'}[a]]=true;
  else if(a==='--reuse-backend')o.startBackend=false;
  else if(['--port','--api-url','--project','--env-file'].includes(a)){
   const value=args[++i];if(!value||value.startsWith('--'))throw Error('Missing value for '+a);
   o[{'--port':'port','--api-url':'api','--project':'project','--env-file':'envFile'}[a]]=a==='--port'?Number(value):value;
  }else throw Error('Unknown option: '+a);
 }
 if(!Number.isInteger(o.port)||o.port<1024||o.port>65535)throw Error('Port must be 1024..65535');
 const u=new URL(o.api);if(u.protocol!=='http:'||!['127.0.0.1','localhost','[::1]'].includes(u.hostname)||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('API must be a loopback HTTP origin. Use an SSH tunnel for a remote Linux backend.');
 o.api=u.origin;if(!/^[a-z0-9][a-z0-9_-]*$/.test(o.project))throw Error('Invalid Compose project name');
 o.envFile=path.resolve(o.envFile);return o;
}
export async function backendStatus(origin){
 try{
  const response=await fetch(origin+'/api/health',{signal:AbortSignal.timeout(4000),redirect:'error'});
  if(!response.ok)return {ready:false,reason:'HTTP '+response.status};
  const h=await response.json();
  return {ready:h.status==='ok'&&h.execution==='gvisor-python'&&h.sandbox_available===true,execution:h.execution,aiAvailable:h.ai_available===true,reason:h.execution!=='gvisor-python'||!h.sandbox_available?'A working gVisor backend is required.':undefined};
 }catch{return {ready:false,reason:'Backend unavailable. Start the existing Linux backend or forward it to this loopback address.'}}
}
function dockerStatus(){
 const r=spawnSync('docker',['info','--format','{"os":{{json .OSType}},"arch":{{json .Architecture}},"runsc":{{if index .Runtimes "runsc"}}true{{else}}false{{end}}}'],{encoding:'utf8',timeout:10000});
 if(r.error||r.status!==0)return {ready:false,reason:'Docker unavailable. A ready backend can still be reused.'};
 try{const d=JSON.parse(r.stdout);return {ready:d.os==='linux'&&d.runsc===true,...d}}catch{return {ready:false,reason:'Cannot read Docker runtime configuration'}}
}
const exists=async p=>{try{await access(p);return true}catch{return false}};
function run(command,args,cwd=root){return new Promise((resolve,reject)=>{const c=spawn(command,args,{cwd,stdio:'inherit',shell:false});c.once('error',reject);c.once('exit',(code,signal)=>code===0?resolve():reject(Error(command+' failed: '+(signal||code))))})}
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function serve(o){
 await new Promise((resolve,reject)=>{const s=net.createServer();s.once('error',()=>reject(Error('Web port is occupied. Use --port; existing processes will not be stopped.')));s.listen(o.port,'127.0.0.1',()=>s.close(resolve))});
 const child=spawn(process.execPath,[path.join(root,'scripts/serve-web.mjs')],{cwd:root,env:{...process.env,DEBUGYCH_WEB_PORT:String(o.port),DEBUGYCH_API_URL:o.api},stdio:['inherit','pipe','inherit']});
 let opened=false;
 child.stdout.on('data',data=>{
  process.stdout.write(data);
  if(o.open&&!opened){opened=true;const command=process.platform==='darwin'?'open':process.platform==='linux'?'xdg-open':null;
   if(command){const browser=spawn(command,[`http://127.0.0.1:${o.port}/`],{stdio:'ignore'});browser.on('error',()=>console.error('Open the printed URL in your browser.'))}
  }
 });
 let stopping=false;const stop=()=>{stopping=true;child.kill('SIGTERM')};process.on('SIGINT',stop);process.on('SIGTERM',stop);
 try{await new Promise((resolve,reject)=>{child.once('error',reject);child.once('exit',(code,signal)=>code===0||stopping||signal==='SIGTERM'?resolve():reject(Error('Web server exited: '+code)))})}
 finally{process.off('SIGINT',stop);process.off('SIGTERM',stop)}
}
export async function main(args=process.argv.slice(2)){
 if(Number(process.versions.node.split('.')[0])<22)throw Error('Node.js 22+ is required. Install it from nodejs.org.');
 const o=options(args);let backend=await backendStatus(o.api);
 if(o.doctor){console.log(JSON.stringify({platform:process.platform,arch:process.arch,node:process.version,frontendBuilt:await exists(path.join(root,'apps/web/dist/index.html')),api:o.api,backend,docker:dockerStatus()},null,2));return backend.ready?0:2}
 if(!backend.ready&&o.startBackend){
  const docker=dockerStatus();if(!docker.ready)throw Error('Compose requires a Linux Docker Engine with registered runsc. Docker Desktop alone is insufficient. See docs/macos.md.');
  if(!await exists(o.envFile))await copyFile(path.join(root,'.env.example'),o.envFile,constants.COPYFILE_EXCL);
  await run('docker',['compose','-p',o.project,'--env-file',o.envFile,'-f',path.join(root,'docker-compose.yml'),'up','-d','--build']);
  for(let i=0;i<60;i++){backend=await backendStatus(o.api);if(backend.ready)break;await pause(2000)}
 }
 if(!backend.ready)throw Error(backend.reason+' See docs/macos.md. No existing containers were stopped.');
 if(!backend.aiAvailable)console.log('Backend connected. AI is not configured; saved results and existing tests remain available.');
 if(o.build||!await exists(path.join(root,'apps/web/dist/index.html'))){
  const web=path.join(root,'apps/web'),npm=process.platform==='win32'?'npm.cmd':'npm';
  if(process.platform==='win32')throw Error('Use scripts/start-local.ps1 -Build on Windows.');
  if(!await exists(path.join(web,'node_modules')))await run(npm,['ci'],web);
  await run(npm,['run','build'],web);
 }
 console.log('Connected to the existing backend. No AI job has been started. Ctrl+C stops only this frontend.');
 await serve(o);return 0;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url))main().then(code=>{process.exitCode=code}).catch(e=>{console.error(e.message);process.exitCode=1});
