const invoke=window.__TAURI__.core.invoke,$=id=>document.getElementById(id);
let busy=false,authBusy=false,savedAccount=false,context,frameOrigin='',frameUrl='',pendingRoute='',frameSession='',frameReady=false,bindingChanging=false;
function clearWorkspace(){frameUrl='';frameOrigin='';frameReady=false;pendingRoute='';$('back').hidden=true;$('workspace').hidden=true;$('workspace').src='about:blank';}
function authControls(value){authBusy=value;for(const id of ['save','account-sign-out','mode','api','account-username','account-password','route-ip','server-token','backend'])$(id).disabled=value;if(!value)$('account-sign-out').disabled=!savedAccount;}
async function accountInfo(){try{const a=await invoke('account_info',{apiUrl:$('api').value.trim()});savedAccount=a.saved;$('account-username').value=a.username||'';$('account-state').textContent=a.saved?'Сохранён сеанс: '+a.username+' · '+({jury:'Жюри',viewer:'Просмотр',team:'Команда',admin:'Администратор'}[a.role]||a.role)+'. Права проверяются при подключении.':'Введите логин и пароль сайта. Пароль в настройки не записывается.';$('account-sign-out').disabled=!a.saved}catch{$('account-state').textContent='Введите логин и пароль. Сохранённый сеанс недоступен.'}}
function currentRoute(){return context?.projectId?'#/workspace/overview?project='+encodeURIComponent(context.projectId):'';}
function postContext(){if(bindingChanging||!frameReady||!frameOrigin)return;if($('workspace').contentWindow)$('workspace').contentWindow.postMessage({type:'debugych-desktop-context',session:frameSession,projectId:context.projectId,revision:context.revision,route:pendingRoute},frameOrigin);pendingRoute='';}
function displayWorkspace(){if(!frameUrl)return;$('startup').hidden=true;$('workspace').hidden=false;$('back').hidden=true;}
function loadFrame(address){const u=new URL(address);if(u.protocol!=='http:'||u.hostname!=='127.0.0.1')throw Error('Некорректный адрес рабочего окна');
 frameOrigin=u.origin;u.searchParams.set('desktop_backend',context.backendUrl);frameSession=crypto.randomUUID();u.searchParams.set('desktop_session',frameSession);u.hash=pendingRoute||currentRoute();const next=u.href;
 if(frameUrl!==next){frameReady=false;frameUrl=next;$('workspace').src=next;}displayWorkspace();}
async function refreshContext(){context=await invoke('get_desktop_context');$('pet-visible').checked=context.petVisible;postContext();}
async function connect(){if(busy)return;busy=true;$('settings').hidden=true;$('retry').hidden=true;$('spinner').hidden=false;try{const address=await invoke('start_application');await refreshContext();loadFrame(address)}catch(e){const message=String(e);$('status').textContent=message;$('retry').hidden=false;$('spinner').hidden=true;if(/Войдите|Сеанс|сеанс|парол/.test(message)){busy=false;clearWorkspace();await configure();$('status').textContent=message}}finally{busy=false}}
async function configure(){if(busy||authBusy)return;$('diagnostic-results').hidden=true;const c=await invoke('get_config');$('config-directory').textContent='Каталог настроек: '+c.config_directory;$('mode').value=c.mode;$('api').value=c.api_url;$('backend').value=c.backend_root;$('route-ip').value=c.route_ip||'';$('root-label').hidden=c.mode!=='local';$('server-auth').hidden=c.mode!=='remote';$('server-token').value='';$('account-password').value='';$('settings').hidden=false;$('startup').hidden=false;$('workspace').hidden=true;$('back').hidden=!frameUrl;$('spinner').hidden=true;document.querySelector('h1').textContent='Подключение Дебагыча';if(c.mode==='remote')await accountInfo();}
$('workspace').onload=postContext;
window.addEventListener('message',async e=>{
 if(bindingChanging||e.source!==$('workspace').contentWindow||e.origin!==frameOrigin||!e.data||typeof e.data!=='object'||e.data.session!==frameSession)return;
 if(e.data.type==='debugych-desktop-auth-required'){clearWorkspace();await configure();$('status').textContent='Сеанс завершён. Войдите снова.';return;}
 if(e.data.type==='debugych-desktop-ready'){frameReady=true;postContext();return;}
 if(e.data.type!=='debugych-desktop-project'||typeof e.data.projectId!=='string'||!Number.isSafeInteger(e.data.revision))return;
 try{context=await invoke('set_selected_project',{projectId:e.data.projectId,revision:e.data.revision})}catch{await refreshContext();}postContext();
});
$('pet-visible').onchange=async()=>{try{context=await invoke('set_pet_visible',{visible:$('pet-visible').checked})}catch(e){$('status').textContent=String(e);$('startup').hidden=false}finally{await refreshContext()}};
$('configure').onclick=$('connection').onclick=()=>configure().catch(e=>$('status').textContent=String(e));$('retry').onclick=connect;$('back').onclick=displayWorkspace;
$('mode').onchange=()=>{$('api').value=$('mode').value==='local'?'http://127.0.0.1:8000':'https://debugych.89-22-232-119.nip.io:9443';$('root-label').hidden=$('mode').value!=='local';$('server-auth').hidden=$('mode').value!=='remote';$('account-password').value=''};
$('save').onclick=async()=>{if(busy||authBusy)return;bindingChanging=true;const config={mode:$('mode').value,api_url:$('api').value.trim(),backend_root:$('backend').value.trim(),route_ip:$('mode').value==='remote'?$('route-ip').value.trim():''};let password=$('account-password').value;const username=$('account-username').value.trim(),secret=$('server-token').value;$('account-password').value='';$('server-token').value='';authControls(true);clearWorkspace();try{await invoke('save_config',{config});if(config.mode==='remote'&&password){$('status').textContent='Вхожу в аккаунт…';await invoke('account_sign_in',{apiUrl:config.api_url,routeIp:config.route_ip,username,password});password=''}else if(config.mode==='remote'&&secret){await invoke('set_server_token',{apiUrl:config.api_url,token:secret})}authControls(false);await connect()}catch(e){password='';$('status').textContent=String(e);$('settings').hidden=false;$('startup').hidden=false;$('spinner').hidden=true}finally{authControls(false);bindingChanging=false;postContext()}};
$('account-sign-out').onclick=async()=>{if(busy||authBusy)return;bindingChanging=true;authControls(true);clearWorkspace();try{await invoke('account_sign_out',{apiUrl:context.backendUrl});authControls(false);await configure();$('status').textContent='Вы вышли. Введите логин и пароль для нового входа.'}catch(e){$('status').textContent=String(e)}finally{authControls(false);bindingChanging=false}};
for(const id of ['account-username','account-password'])$(id).addEventListener('keydown',event=>{if(event.key==='Enter'&&!busy&&!authBusy){event.preventDefault();$('save').click()}});
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
