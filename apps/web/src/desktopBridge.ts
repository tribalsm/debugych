/** Minimal native-host bridge. The web app has no privileged Tauri API. */
let revision=-1,pending:string|undefined;
const embedded=window.parent!==window;
const host='http://tauri.localhost';
const binding=new URLSearchParams(location.search).get('desktop_backend');
const session=new URLSearchParams(location.search).get('desktop_session');
export function requestDesktopLogin(){if(embedded&&session)window.parent.postMessage({type:'debugych-desktop-auth-required',session},host);}
if(embedded&&binding){if(localStorage.getItem('debugych-desktop-backend')!==binding)localStorage.removeItem('debugych-project');localStorage.setItem('debugych-desktop-backend',binding);}
export function publishDesktopProject(projectId:string){if(!embedded||revision<0)return;if(pending!==undefined&&pending!==projectId)return;pending=undefined;window.parent.postMessage({type:'debugych-desktop-project',projectId,revision,session},host);}
export function connectDesktopProject(select:(id:string)=>void,current:()=>string){
 if(!embedded)return()=>{};
 const receive=(e:MessageEvent)=>{if(e.source!==window.parent||e.origin!==host||e.data?.type!=='debugych-desktop-context'||e.data.session!==session||!Number.isSafeInteger(e.data.revision)||e.data.revision<revision)return;
  const id=e.data.projectId;if(typeof id!=='string'||(id!==''&&!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(id)))return;const initial=revision<0;revision=e.data.revision;
  if(id){if(id===current())pending=undefined;else{pending=id;select(id);}}
  else if(initial){const saved=current()||localStorage.getItem('debugych-project');if(saved)publishDesktopProject(saved);}
  else if(current()){pending='';select('');}
  if(typeof e.data.route==='string'&&/^#\/workspace\/(overview|tests|bugs|report)\?project=/.test(e.data.route))location.hash=e.data.route;
 };
 window.addEventListener('message',receive);window.parent.postMessage({type:'debugych-desktop-ready',session},host);return()=>window.removeEventListener('message',receive);
}
