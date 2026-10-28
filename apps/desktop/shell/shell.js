const invoke=window.__TAURI__.core.invoke,$=id=>document.getElementById(id);
let busy=false,context,frameOrigin='',frameUrl='',pendingRoute='',frameSession='',frameReady=false,bindingChanging=false;
function currentRoute(){return context?.projectId?'#/workspace/overview?project='+encodeURIComponent(context.projectId):'';}
function postContext(){if(bindingChanging||!frameReady||!frameOrigin)return;if($('workspace').contentWindow)$('workspace').contentWindow.postMessage({type:'debugych-desktop-context',session:frameSession,projectId:context.projectId,revision:context.revision,route:pendingRoute},frameOrigin);pendingRoute='';}
function displayWorkspace(){if(!frameUrl)return;$('startup').hidden=true;$('workspace').hidden=false;$('back').hidden=true;}
function loadFrame(address){const u=new URL(address);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1')throw Error('Некорректный адрес рабочего окна');
 frameOrigin=u.origin;u.searchParams.set('desktop_backend',context.backendUrl);frameSession=crypto.randomUUID();u.searchParams.set('desktop_session',frameSession);u.hash=pendingRoute||currentRoute();const next=u.href;
 if(frameUrl!==next){frameReady=false;frameUrl=next;$('workspace').src=next;}displayWorkspace();}
async function refreshContext(){context=await invoke('get_desktop_context');$('pet-visible').checked=context.petVisible;postContext();}
async function connect(){if(busy)return;busy=true;$('settings').hidden=true;$('retry').hidden=true;$('spinner').hidden=false;try{const address=await invoke('start_application');await refreshContext();loadFrame(address)}catch(e){$('status').textContent=String(e);$('retry').hidden=false;$('spinner').hidden=true}finally{busy=false}}
async function configure(){if(busy)return;$('diagnostic-results').hidden=true;const c=await invoke('get_config');$('config-directory').textContent='Каталог настроек: '+c.config_directory;$('mode').value=c.mode;$('api').value=c.api_url;$('backend').value=c.backend_root;$('root-label').hidden=c.mode!=='local';$('server-auth').hidden=c.mode!=='remote';$('server-token').value='';$('settings').hidden=false;$('startup').hidden=false;$('workspace').hidden=true;$('back').hidden=!frameUrl;$('spinner').hidden=true;document.querySelector('h1').textContent='Подключение Дебагыча';}
$('workspace').onload=postContext;
window.addEventListener('message',async e=>{
 if(bindingChanging||e.source!==$('workspace').contentWindow||e.origin!==frameOrigin||!e.data||typeof e.data!=='object'||e.data.session!==frameSession)return;
 if(e.data.type==='debugych-desktop-ready'){frameReady=true;postContext();return;}
 if(e.data.type!=='debugych-desktop-project'||typeof e.data.projectId!=='string'||!Number.isSafeInteger(e.data.revision))return;
 try{context=await invoke('set_selected_project',{projectId:e.data.projectId,revision:e.data.revision})}catch{await refreshContext();}postContext();
});
$('pet-visible').onchange=async()=>{try{context=await invoke('set_pet_visible',{visible:$('pet-visible').checked})}catch(e){$('status').textContent=String(e);$('startup').hidden=false}finally{await refreshContext()}};
$('configure').onclick=$('connection').onclick=()=>configure().catch(e=>$('status').textContent=String(e));$('retry').onclick=connect;$('back').onclick=displayWorkspace;
$('mode').onchange=()=>{$('api').value=$('mode').value==='local'?'http://127.0.0.1:8000':'https://';$('root-label').hidden=$('mode').value!=='local';$('server-auth').hidden=$('mode').value!=='remote'};
$('save').onclick=async()=>{bindingChanging=true;try{const secret=$('server-token').value;$('server-token').value='';if($('mode').value==='remote'&&secret)await invoke('set_server_token',{apiUrl:$('api').value.trim(),token:secret});await invoke('save_config',{config:{mode:$('mode').value,api_url:$('api').value.trim(),backend_root:$('backend').value.trim()}});frameUrl='';frameOrigin='';frameReady=false;pendingRoute='';$('back').hidden=true;$('workspace').src='about:blank';await connect()}catch(e){$('status').textContent=String(e)}finally{bindingChanging=false;postContext()}};
setInterval(async()=>{try{const s=await invoke('startup_status');if(s)$('status').textContent=s}catch{}},700);
async function initialize(){
await window.__TAURI__.event.listen('desktop-context',e=>{if(context&&e.payload.revision<context.revision)return;context=e.payload;$('pet-visible').checked=context.petVisible;postContext();});
await window.__TAURI__.event.listen('desktop-settings',()=>configure());
await window.__TAURI__.event.listen('desktop-navigate',e=>{pendingRoute='#'+e.payload;displayWorkspace();postContext();});
await refreshContext();await connect();

}
initialize().catch(error=>{$("status").textContent="Не удалось запустить native-интеграцию: "+String(error);$("spinner").hidden=true;$("retry").hidden=false;});

async function diagnose(){
 if(busy)return;const box=$('diagnostic-results');box.hidden=false;box.textContent='Проверяю API и окружение. Платные AI-запросы не выполняются.';
 $('startup').hidden=false;$('workspace').hidden=true;$('back').hidden=!frameUrl;$('spinner').hidden=true;document.querySelector('h1').textContent='Проверка окружения';
 $('diagnostics').disabled=true;
 try{const checks=await invoke('environment_diagnostics');box.replaceChildren();for(const check of checks){const item=document.createElement('article');item.className='diagnostic '+check.status;const title=document.createElement('strong');title.textContent=check.name+' · '+({pass:'Готово',fail:'Недоступно',warning:'Требует внимания',not_applicable:'Не требуется'}[check.status]||check.status);const detail=document.createElement('p');detail.textContent=check.detail;item.append(title,detail);box.append(item)}}catch(e){box.textContent='Диагностика не завершена: '+String(e)}finally{$('diagnostics').disabled=false}
}
$('diagnostics').onclick=diagnose;
window.__TAURI__.event.listen('desktop-diagnostics',diagnose);

$('remove-server-token').onclick=async()=>{try{await invoke('set_server_token',{apiUrl:$('api').value.trim(),token:''});$('server-token-state').textContent='Сохранённый токен удалён. Потребуется новый токен и повторное подключение.'}catch{$('server-token-state').textContent='Не удалось изменить Windows Credential Manager.'}};
