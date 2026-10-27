#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{fs,path::PathBuf,process::{Command,Stdio},sync::Mutex,time::{Duration,Instant},net::TcpListener};
use serde::{Deserialize,Serialize};
use tauri::{Emitter,Manager,State,menu::{Menu,MenuItem}};
use std::sync::atomic::{AtomicBool,Ordering};
mod diagnostics;mod legacy;mod owned_process;mod backend;mod pet;use owned_process::OwnedChild;
#[cfg(windows)]use std::os::windows::process::CommandExt;
#[derive(Clone,Serialize,Deserialize)]
#[serde(default)]
struct Config{mode:String,api_url:String,backend_root:String,pet_visible:bool,project_id:String,#[serde(skip)]revision:u64}
impl Default for Config{fn default()->Self{Self{mode:"local".into(),api_url:"http://127.0.0.1:8000".into(),backend_root:String::new(),pet_visible:false,project_id:String::new(),revision:0}}}
fn valid(c:&Config)->bool{let Ok(u)=reqwest::Url::parse(&c.api_url)else{return false};let local=matches!(u.host_str(),Some("127.0.0.1"|"localhost"|"[::1]"|"::1"));u.username().is_empty()&&u.password().is_none()&&u.path()=="/"&&u.query().is_none()&&u.fragment().is_none()&&(c.project_id.is_empty()||backend::valid_id(&c.project_id))&&match c.mode.as_str(){"local"=>local&&u.scheme()=="http","remote"=>u.scheme()=="https",_=>false}}
struct Runtime{config:Mutex<Config>,status:Mutex<String>,busy:Mutex<bool>,web:Mutex<Option<OwnedChild>>,wsl:Mutex<Option<OwnedChild>>,bootstrap:Mutex<Option<OwnedChild>>,frontend:Mutex<String>,closing:AtomicBool,context_gate:Mutex<()>}
fn command(exe:impl AsRef<std::ffi::OsStr>)->Command{let mut c=Command::new(exe);#[cfg(windows)]c.creation_flags(0x08000000);c}
fn config_dir(app:&tauri::AppHandle)->Result<PathBuf,String>{
 if let Ok(p)=std::env::var("DEBUGYCH_DESKTOP_PROFILE"){let p=PathBuf::from(p);if p.is_absolute(){return Ok(p)}}
 // The new single-instance identifier must not move existing 1.1 user data.
 app.path().app_config_dir().map(|p|p.with_file_name("local.debugych.desktop")).map_err(|_|"Каталог настроек недоступен".into())
}
fn config_path(app:&tauri::AppHandle)->Result<PathBuf,String>{Ok(config_dir(app)?.join("connection.json"))}
fn persist(app:&tauri::AppHandle,c:&Config)->Result<(),String>{let p=config_path(app)?;fs::create_dir_all(p.parent().unwrap()).map_err(|_|"Не удалось создать каталог настроек")?;let temp=p.with_extension("json.tmp");fs::write(&temp,serde_json::to_vec(c).unwrap()).map_err(|_|"Не удалось сохранить настройки")?;fs::rename(temp,p).map_err(|_|"Не удалось сохранить настройки".into())}
#[derive(Clone,Serialize)]#[serde(rename_all="camelCase")]
struct DesktopContext{backend_url:String,frontend_url:String,project_id:String,revision:u64,pet_visible:bool}
fn context(app:&tauri::AppHandle)->DesktopContext{let r=app.state::<Runtime>();let c=r.config.lock().unwrap();let frontend_url=r.frontend.lock().unwrap().clone();DesktopContext{backend_url:c.api_url.trim_end_matches('/').into(),frontend_url,project_id:c.project_id.clone(),revision:c.revision,pet_visible:c.pet_visible}}
fn broadcast_context(app:&tauri::AppHandle){let c=context(app);app.state::<backend::Backend>().set_context(&c.backend_url,&c.frontend_url,&c.project_id);let _=app.emit("desktop-context",c);}
#[tauri::command]fn get_desktop_context(app:tauri::AppHandle)->DesktopContext{context(&app)}
#[tauri::command]fn get_config(app:tauri::AppHandle,state:State<Runtime>)->serde_json::Value{let mut value=serde_json::to_value(state.config.lock().unwrap().clone()).unwrap();value["config_directory"]=serde_json::json!(config_dir(&app).unwrap_or_default());value}
#[tauri::command]fn startup_status(state:State<Runtime>)->String{state.status.lock().unwrap().clone()}
#[tauri::command]fn save_config(app:tauri::AppHandle,state:State<Runtime>,mut config:Config)->Result<(),String>{
 if *state.busy.lock().unwrap(){return Err("Дождитесь завершения запуска".into())}
 if !valid(&config){return Err("Локальный API: HTTP localhost; сервер: HTTPS без ключей и пути в URL".into())}
 let _gate=state.context_gate.lock().unwrap();let mut old=state.config.lock().unwrap();let changed=old.api_url!=config.api_url||old.mode!=config.mode;config.pet_visible=old.pet_visible;config.project_id=if old.api_url==config.api_url{old.project_id.clone()}else{String::new()};config.revision=old.revision+1;persist(&app,&config)?;*old=config;drop(old);if changed{state.web.lock().unwrap().take();state.frontend.lock().unwrap().clear();if state.config.lock().unwrap().mode=="remote"{state.wsl.lock().unwrap().take();}}broadcast_context(&app);Ok(())
}
fn select_project(app:&tauri::AppHandle,id:String,expected:Option<u64>)->Result<DesktopContext,String>{
 if !id.is_empty()&&!backend::valid_id(&id){return Err("Некорректный проект".into())}
 let r=app.state::<Runtime>();let _gate=r.context_gate.lock().unwrap();let mut c=r.config.lock().unwrap();
 if expected.is_some_and(|e|e!=c.revision){return Err("Контекст изменился. Повторите действие.".into())}
 if c.project_id!=id {let mut next=c.clone();next.project_id=id;next.revision+=1;persist(app,&next)?;*c=next;}
 drop(c);broadcast_context(app);Ok(context(app))
}
#[tauri::command]fn set_selected_project(app:tauri::AppHandle,project_id:String,revision:u64)->Result<DesktopContext,String>{select_project(&app,project_id,Some(revision))}
fn set_pet_visible_inner(app:&tauri::AppHandle,visible:bool)->Result<DesktopContext,String>{
 let r=app.state::<Runtime>();let _gate=r.context_gate.lock().unwrap();{let mut c=r.config.lock().unwrap();let mut next=c.clone();next.pet_visible=visible;next.revision+=1;persist(app,&next)?;*c=next;}
 if let Some(w)=app.get_webview_window("pet"){if visible{pet::show(&w);}else{let _=w.emit("pet-visibility",false);w.hide().map_err(|_|"Не удалось скрыть питомца")?;app.state::<backend::Backend>().cancel_all();}}
 broadcast_context(app);Ok(context(app))
}
#[tauri::command]fn set_pet_visible(app:tauri::AppHandle,visible:bool)->Result<DesktopContext,String>{set_pet_visible_inner(&app,visible)}
fn restore_main(app:&tauri::AppHandle)->Result<(),String>{let w=app.get_webview_window("main").ok_or("Основное окно недоступно")?;if w.is_minimized().map_err(|_|"Окно недоступно")?{w.unminimize().map_err(|_|"Окно недоступно")?;}w.show().map_err(|_|"Окно недоступно")?;w.set_focus().map_err(|_|"Окно недоступно".into())}
#[tauri::command]fn open_main_window(app:tauri::AppHandle)->Result<(),String>{restore_main(&app)}
#[tauri::command]fn show_connection_settings(app:tauri::AppHandle)->Result<(),String>{restore_main(&app)?;app.emit("desktop-settings",true).map_err(|_|"Настройки недоступны".into())}
fn own_spawn(app:&tauri::AppHandle,slot:&Mutex<Option<OwnedChild>>,command:&mut Command)->Result<(),String>{let r=app.state::<Runtime>();let mut child=slot.lock().unwrap();if r.closing.load(Ordering::SeqCst){return Err("Приложение завершается".into())}*child=Some(OwnedChild::spawn(command).map_err(|_|"Не удалось запустить локальный процесс приложения")?);Ok(())}
fn health(client:&reqwest::blocking::Client,url:&str)->bool{client.get(format!("{}/api/health",url.trim_end_matches('/'))).send().ok().filter(|r|r.status().is_success()).and_then(|r|r.json::<serde_json::Value>().ok()).map_or(false,|h|h["status"]=="ok"&&h["execution"]=="gvisor-python"&&h["sandbox_available"]==true)}
fn boot(app:&tauri::AppHandle)->Result<String,String>{
 let conflicts=legacy::conflicts();if !conflicts.is_empty(){return Err(format!("Работает старая portable-версия. Закройте её через меню Выход и нажмите Повторить. Данные и старые ярлыки сохранены.\n{}",conflicts.join("\n")))}
 let state=app.state::<Runtime>();let c=state.config.lock().unwrap().clone();if !valid(&c){return Err("Проверьте настройки подключения".into())}
 let root=std::env::current_exe().map_err(|_|"Каталог приложения недоступен")?.parent().unwrap().join("resources");
 let data=config_dir(app)?;fs::create_dir_all(&data).map_err(|_|"Не удалось создать каталог данных")?;
 let client=reqwest::blocking::Client::builder().timeout(Duration::from_secs(4)).redirect(reqwest::redirect::Policy::none()).no_proxy().build().map_err(|_|"HTTP клиент недоступен")?;
 *state.status.lock().unwrap()="Проверяю backend и gVisor...".into();
 if c.mode=="local"&&state.wsl.lock().unwrap().is_none(){
  let _=own_spawn(app,&state.wsl,command("wsl.exe").args(["-d","Ubuntu","-u","root","--","sh","-c","read -r debugych_keepalive"]).stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null()));
 }
 if !health(&client,&c.api_url){
  if c.mode=="remote"{return Err("Сервер недоступен или gVisor не готов. Проверьте адрес и подключение. Локальный стек не изменялся.".into())}
  if c.api_url.trim_end_matches('/')!="http://127.0.0.1:8000"{return Err("Автозапуск локального backend использует 127.0.0.1:8000. Для другого адреса сначала запустите его отдельно.".into())}
  *state.status.lock().unwrap()="Запускаю локальный backend. При первом запуске сборка контейнеров может занять несколько минут...".into();
  let backend=if c.backend_root.is_empty(){root.join("backend")}else{PathBuf::from(&c.backend_root)};
  let log=data.join("backend-startup.log");
  own_spawn(app,&state.bootstrap,command("powershell.exe").args(["-NoLogo","-NoProfile","-NonInteractive","-Command"]).arg(include_str!("../../../scripts/ensure-backend.ps1")).env("DEBUGYCH_BACKEND_ROOT",backend).env("DEBUGYCH_DATA_DIR",&data).env("DEBUGYCH_BOOT_LOG",&log).stdout(Stdio::null()).stderr(Stdio::null()))?;
  let bootstrap_deadline=Instant::now()+Duration::from_secs(300);let result=loop{if Instant::now()>bootstrap_deadline{state.bootstrap.lock().unwrap().take();return Err("Запуск backend не завершился. Проверьте WSL/Docker и повторите подключение.".into())}if state.closing.load(Ordering::SeqCst){return Err("Приложение завершается".into())}let status=state.bootstrap.lock().unwrap().as_mut().ok_or("Bootstrap остановлен")?.try_wait().map_err(|_|"Ошибка bootstrap")?;if let Some(status)=status{state.bootstrap.lock().unwrap().take();break status}std::thread::sleep(Duration::from_millis(150));};
  if !result.success(){let reason=fs::read_to_string(data.join("startup-error.txt")).unwrap_or_else(|_|"Backend не запущен. Проверьте WSL2, Linux Docker и gVisor.".into());return Err(format!("{}\nДиагностика: {}",reason.chars().take(700).collect::<String>(),log.display()))}
  let deadline=Instant::now()+Duration::from_secs(90);while !health(&client,&c.api_url){if Instant::now()>deadline{return Err("Backend не стал готов за 90 секунд. Откройте настройки или повторите подключение.".into())}std::thread::sleep(Duration::from_secs(2));}
 }
 *state.status.lock().unwrap()="Backend готов. Открываю Дебагыча...".into();
 state.web.lock().unwrap().take();
 let port_file=data.join("frontend-port.txt");let preferred=fs::read_to_string(&port_file).ok().and_then(|s|s.trim().parse::<u16>().ok()).filter(|p|*p>=1024).unwrap_or(0);
 let socket=TcpListener::bind(("127.0.0.1",preferred)).map_err(|_|"Порт приложения занят другим процессом. Закройте другую копию или проверьте frontend-port.txt в каталоге данных.")?;let port=socket.local_addr().unwrap().port();drop(socket);fs::write(port_file,port.to_string()).map_err(|_|"Не удалось сохранить адрес приложения")?;
 let log=fs::OpenOptions::new().create(true).append(true).open(data.join("frontend.log")).map_err(|_|"Не удалось открыть журнал запуска")?;
 own_spawn(app,&state.web,command(root.join("runtime/node.exe")).arg(root.join("scripts/serve-web.mjs")).env("DEBUGYCH_WEB_PORT",port.to_string()).env("DEBUGYCH_API_URL",&c.api_url).env("DEBUGYCH_DESKTOP_EMBED","1").env("DEBUGYCH_ALLOW_REMOTE_API",if c.mode=="remote"{"1"}else{"0"}).stdout(Stdio::null()).stderr(log))?;
 let address=format!("http://127.0.0.1:{port}/");
 let deadline=Instant::now()+Duration::from_secs(15);while !client.get(&address).send().map_or(false,|r|r.status().is_success()){if Instant::now()>deadline{return Err("Не удалось открыть встроенный frontend. Проверьте комплект ресурсов и frontend.log.".into())}std::thread::sleep(Duration::from_millis(200));}
 *state.frontend.lock().unwrap()=address.trim_end_matches('/').into();broadcast_context(app);Ok(address)
}
#[tauri::command]async fn environment_diagnostics(app:tauri::AppHandle)->Result<Vec<diagnostics::Check>,String>{let c=app.state::<Runtime>().config.lock().unwrap().clone();let folder=config_dir(&app)?;tauri::async_runtime::spawn_blocking(move||diagnostics::run(&c,&folder)).await.map_err(|_|"Ошибка диагностики".into())}
#[tauri::command]async fn start_application(app:tauri::AppHandle)->Result<String,String>{let state=app.state::<Runtime>();{let mut b=state.busy.lock().unwrap();if *b{return Err("Запуск уже выполняется".into())}*b=true;}let copy=app.clone();let result=tauri::async_runtime::spawn_blocking(move||boot(&copy)).await.map_err(|_|"Ошибка запуска приложения".to_string()).and_then(|r|r);if let Err(ref error)=result{*app.state::<Runtime>().status.lock().unwrap()=error.clone();}*app.state::<Runtime>().busy.lock().unwrap()=false;result}
fn main(){
 std::panic::set_hook(Box::new(|info|{use std::io::Write;if let Ok(exe)=std::env::current_exe(){let message=info.to_string().chars().take(1800).collect::<String>();if let Ok(mut log)=fs::OpenOptions::new().create(true).append(true).open(exe.parent().unwrap().join("native-startup-error.txt")){let _=writeln!(log,"{message}");}}}));
 let mut ctx=tauri::generate_context!();
 if std::env::var_os("DEBUGYCH_DESKTOP_PROFILE").is_some(){use std::hash::{Hash,Hasher};let mut hash=std::collections::hash_map::DefaultHasher::new();std::env::var_os("DEBUGYCH_DESKTOP_PROFILE").hash(&mut hash);ctx.config_mut().identifier.push_str(&format!(".qa{:x}",hash.finish()));}
 let app=tauri::Builder::default().plugin(tauri_plugin_single_instance::init(|app,_,_|{let _=restore_main(app);}))
 .setup(|app|{
  let path=config_path(app.handle()).unwrap();let cfg=fs::read(path).ok().and_then(|b|serde_json::from_slice::<Config>(&b).ok()).filter(valid).unwrap_or_default();
  app.manage(Runtime{config:Mutex::new(cfg),status:Mutex::new(String::new()),busy:Mutex::new(false),web:Mutex::new(None),wsl:Mutex::new(None),bootstrap:Mutex::new(None),frontend:Mutex::new(String::new()),closing:AtomicBool::new(false),context_gate:Mutex::new(())});
  let folder=config_dir(app.handle())?;
  if let Ok(exe)=std::env::current_exe(){let _=fs::write(exe.parent().unwrap().join("native-runtime.json"),serde_json::json!({"configDirectory":folder,"processId":std::process::id()}).to_string());}
  migrate_pet(&folder)?;app.manage(backend::Backend::load(folder.join("pet/companion.json"))?);broadcast_context(app.handle());
  // Windows can execute an embedded page before Builder::setup completes.
  // Create the pet blank, initialize all native state, then allow its scripts.
  let mut pet_config=app.config().app.windows.iter().find(|w|w.label=="pet").unwrap().clone();
  pet_config.url=tauri::WebviewUrl::External("about:blank".parse()?);
  let pet_window=tauri::WebviewWindowBuilder::from_config(app,&pet_config)?.build()?;
  pet::setup(app.handle())?;
  pet_window.navigate("http://tauri.localhost/pet/index.html".parse()?)?;
  let main_config=app.config().app.windows.iter().find(|w|w.label=="main").unwrap().clone();
  tauri::WebviewWindowBuilder::from_config(app,&main_config)?.build()?;
  let connection=MenuItem::with_id(app,"connection","Подключение",true,None::<&str>)?;let pet=MenuItem::with_id(app,"pet","Показать / скрыть питомца",true,None::<&str>)?;let quit=MenuItem::with_id(app,"quit","Выход",true,None::<&str>)?;app.get_webview_window("main").unwrap().set_menu(Menu::with_items(app,&[&connection,&pet,&quit])?)?;
  let open=MenuItem::with_id(app,"open","Открыть Дебагыч",true,None::<&str>)?;let diagnostics=MenuItem::with_id(app,"diagnostics","Проверка окружения",true,None::<&str>)?;
  let mut tray=tauri::tray::TrayIconBuilder::new().tooltip("Дебагыч Desktop 1.2").menu(&Menu::with_items(app,&[&open,&pet,&diagnostics,&connection,&quit])?).show_menu_on_left_click(true);if let Some(icon)=app.default_window_icon(){tray=tray.icon(icon.clone());}tray.build(app)?;Ok(())
 })
 .on_menu_event(|app,event|match event.id().as_ref(){"open"=>{let _=restore_main(app);},"diagnostics"=>{let _=restore_main(app);let _=app.emit("desktop-diagnostics",true);},"connection"=>{let _=show_connection_settings(app.clone());},"pet"=>{let _=set_pet_visible_inner(app,!context(app).pet_visible);},"quit"=>app.exit(0),_=>{}})
 .on_window_event(|window,event|{if window.label()=="main"{if let tauri::WindowEvent::CloseRequested{api,..}=event{api.prevent_close();window.app_handle().exit(0);}}})
 .invoke_handler(tauri::generate_handler![environment_diagnostics,get_config,startup_status,save_config,start_application,get_desktop_context,set_selected_project,set_pet_visible,open_main_window,show_connection_settings,pet::set_expanded,pet::pet_ready,pet::drag_pet,pet::get_preferences,pet::set_motion,pet::set_size,pet::set_panel_height,pet::hide_pet,backend::get_companion_settings,backend::save_companion_config,backend::save_companion_seen,backend::backend_get,backend::cancel_backend_read,backend::open_companion_page,backend::companion_post,backend::get_chat_history,backend::save_chat_history]).build(ctx).expect("Debugych startup");
 app.run(|app,event|{if matches!(event,tauri::RunEvent::Exit){let state=app.state::<Runtime>();state.closing.store(true,Ordering::SeqCst);app.state::<backend::Backend>().cancel_all();for slot in [&state.bootstrap,&state.web,&state.wsl]{slot.lock().unwrap().take();}}});
}
fn migrate_pet(folder:&std::path::Path)->std::io::Result<()>{
 let Some(appdata)=std::env::var_os("APPDATA")else{return Ok(())};let legacy=PathBuf::from(appdata).join("local.debugych.desktoppet.v2");
 if std::env::var_os("DEBUGYCH_DESKTOP_PROFILE").is_none(){for name in ["preferences.json","companion.json","chat-history.json"]{let target=folder.join("pet").join(name);let source=legacy.join(name);if !target.exists()&&source.is_file()&&source.metadata()?.len()<=65536{fs::create_dir_all(target.parent().unwrap())?;fs::copy(source,target)?;}}}Ok(())
}
#[cfg(test)]mod tests{use super::*;#[test]fn endpoints_do_not_accept_keys_cleartext_remote_or_local_paths(){assert!(valid(&Config::default()));for u in ["http://example.com","https://user:secret@example.com","https://example.com/api","https://example.com/#key"]{assert!(!valid(&Config{mode:"remote".into(),api_url:u.into(),..Config::default()}));}assert!(valid(&Config{mode:"remote".into(),api_url:"https://example.com".into(),..Config::default()}));}}
