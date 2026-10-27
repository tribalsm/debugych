const invoke=window.__TAURI__.core.invoke,$=id=>document.getElementById(id);let busy=false;
async function connect(){if(busy)return;busy=true;$('settings').hidden=true;$('retry').hidden=true;$('spinner').hidden=false;try{await invoke('start_application')}catch(e){$('status').textContent=String(e);$('retry').hidden=false;$('spinner').hidden=true}finally{busy=false}}
async function configure(){if(busy)return;const c=await invoke('get_config');$('mode').value=c.mode;$('api').value=c.api_url;$('backend').value=c.backend_root;$('root-label').hidden=c.mode!=='local';$('settings').hidden=!$('settings').hidden;$('spinner').hidden=true;document.querySelector('h1').textContent='Подключение Дебагыча'}
$('configure').onclick=()=>configure().catch(e=>$('status').textContent=String(e));$('retry').onclick=connect;
$('mode').onchange=()=>{$('api').value=$('mode').value==='local'?'http://127.0.0.1:8000':'https://';$('root-label').hidden=$('mode').value!=='local'};
$('save').onclick=async()=>{try{await invoke('save_config',{config:{mode:$('mode').value,api_url:$('api').value.trim(),backend_root:$('backend').value.trim()}});await connect()}catch(e){$('status').textContent=String(e)}};
setInterval(async()=>{try{const s=await invoke('startup_status');if(s)$('status').textContent=s}catch{}},700);
if(new URLSearchParams(location.search).has('settings'))configure();else connect();
