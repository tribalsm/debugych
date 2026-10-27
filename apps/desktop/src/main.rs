#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{fs,path::PathBuf,process::{Child,Command,Stdio},sync::Mutex,time::{Duration,Instant},net::TcpListener};
use serde::{Deserialize,Serialize};
use tauri::{Manager,State,menu::{Menu,MenuItem}};
#[cfg(windows)]use std::os::windows::process::CommandExt;
#[derive(Clone,Serialize,Deserialize)]
#[serde(default)]
struct Config{mode:String,api_url:String,backend_root:String}
impl Default for Config{fn default()->Self{Self{mode:"local".into(),api_url:"http://127.0.0.1:8000".into(),backend_root:String::new()}}}
fn valid(c:&Config)->bool{let Ok(u)=reqwest::Url::parse(&c.api_url)else{return false};let local=matches!(u.host_str(),Some("127.0.0.1"|"localhost"|"[::1]"|"::1"));u.username().is_empty()&&u.password().is_none()&&u.path()=="/"&&u.query().is_none()&&u.fragment().is_none()&&match c.mode.as_str(){"local"=>local&&u.scheme()=="http","remote"=>u.scheme()=="https",_=>false}}
struct Runtime{config:Mutex<Config>,status:Mutex<String>,busy:Mutex<bool>,web:Mutex<Option<Child>>,wsl:Mutex<Option<Child>>}
fn command(exe:impl AsRef<std::ffi::OsStr>)->Command{let mut c=Command::new(exe);#[cfg(windows)]c.creation_flags(0x08000000);c}
fn config_path(app:&tauri::AppHandle)->Result<PathBuf,String>{app.path().app_config_dir().map(|p|p.join("connection.json")).map_err(|_|"Каталог настроек недоступен".into())}
#[tauri::command]fn get_config(state:State<Runtime>)->Config{state.config.lock().unwrap().clone()}
#[tauri::command]fn startup_status(state:State<Runtime>)->String{state.status.lock().unwrap().clone()}
#[tauri::command]fn save_config(app:tauri::AppHandle,state:State<Runtime>,config:Config)->Result<(),String>{if *state.busy.lock().unwrap(){return Err("Дождитесь завершения запуска".into())}if !valid(&config){return Err("Локальный API: HTTP localhost; сервер: HTTPS без ключей и пути в URL".into())}let p=config_path(&app)?;fs::create_dir_all(p.parent().unwrap()).map_err(|_|"Не удалось сохранить настройки")?;fs::write(p,serde_json::to_vec(&config).unwrap()).map_err(|_|"Не удалось сохранить настройки")?;*state.config.lock().unwrap()=config;Ok(())}
fn health(client:&reqwest::blocking::Client,url:&str)->bool{client.get(format!("{}/api/health",url.trim_end_matches('/'))).send().ok().filter(|r|r.status().is_success()).and_then(|r|r.json::<serde_json::Value>().ok()).map_or(false,|h|h["status"]=="ok"&&h["execution"]=="gvisor-python"&&h["sandbox_available"]==true)}
fn boot(app:&tauri::AppHandle)->Result<(),String>{
 let state=app.state::<Runtime>();let c=state.config.lock().unwrap().clone();if !valid(&c){return Err("Проверьте настройки подключения".into())}
 let root=std::env::current_exe().map_err(|_|"Каталог приложения недоступен")?.parent().unwrap().join("resources");
 let data=app.path().app_data_dir().map_err(|_|"Каталог данных недоступен")?;fs::create_dir_all(&data).map_err(|_|"Не удалось создать каталог данных")?;
 let client=reqwest::blocking::Client::builder().timeout(Duration::from_secs(4)).redirect(reqwest::redirect::Policy::none()).no_proxy().build().map_err(|_|"HTTP клиент недоступен")?;
 *state.status.lock().unwrap()="Проверяю backend и gVisor...".into();
 if c.mode=="local"&&state.wsl.lock().unwrap().is_none()&&command("wsl.exe").args(["--status"]).stdout(Stdio::null()).stderr(Stdio::null()).status().map_or(false,|s|s.success()){
  *state.wsl.lock().unwrap()=command("wsl.exe").args(["-d","Ubuntu","-u","root","--","sh","-c","read -r debugych_keepalive"]).stdin(Stdio::piped()).stdout(Stdio::null()).stderr(Stdio::null()).spawn().ok();
 }
 if !health(&client,&c.api_url){
  if c.mode=="remote"{return Err("Сервер недоступен или gVisor не готов. Проверьте адрес и подключение. Локальный стек не изменялся.".into())}
  if c.api_url.trim_end_matches('/')!="http://127.0.0.1:8000"{return Err("Автозапуск локального backend использует 127.0.0.1:8000. Для другого адреса сначала запустите его отдельно.".into())}
  *state.status.lock().unwrap()="Запускаю локальный backend. При первом запуске сборка контейнеров может занять несколько минут...".into();
  let backend=if c.backend_root.is_empty(){root.join("backend")}else{PathBuf::from(&c.backend_root)};
  let log=data.join("backend-startup.log");
  let result=command("powershell.exe").args(["-NoLogo","-NoProfile","-NonInteractive","-Command"]).arg(include_str!("../../../scripts/ensure-backend.ps1")).env("DEBUGYCH_BACKEND_ROOT",backend).env("DEBUGYCH_DATA_DIR",&data).env("DEBUGYCH_BOOT_LOG",&log).stdout(Stdio::null()).stderr(Stdio::null()).status().map_err(|_|"Не удалось запустить bootstrap backend")?;
  if !result.success(){let reason=fs::read_to_string(data.join("startup-error.txt")).unwrap_or_else(|_|"Backend не запущен. Проверьте WSL2, Linux Docker и gVisor.".into());return Err(format!("{}\nДиагностика: {}",reason.chars().take(700).collect::<String>(),log.display()))}
  let deadline=Instant::now()+Duration::from_secs(90);while !health(&client,&c.api_url){if Instant::now()>deadline{return Err("Backend не стал готов за 90 секунд. Откройте настройки или повторите подключение.".into())}std::thread::sleep(Duration::from_secs(2));}
 }
 *state.status.lock().unwrap()="Backend готов. Открываю Дебагыча...".into();
 if let Some(mut old)=state.web.lock().unwrap().take(){let _=old.kill();let _=old.wait();}
 let port_file=data.join("frontend-port.txt");let preferred=fs::read_to_string(&port_file).ok().and_then(|s|s.trim().parse::<u16>().ok()).filter(|p|*p>=1024).unwrap_or(0);
 let socket=TcpListener::bind(("127.0.0.1",preferred)).map_err(|_|"Порт приложения занят другим процессом. Закройте другую копию или проверьте frontend-port.txt в каталоге данных.")?;let port=socket.local_addr().unwrap().port();drop(socket);fs::write(port_file,port.to_string()).map_err(|_|"Не удалось сохранить адрес приложения")?;
 let log=fs::OpenOptions::new().create(true).append(true).open(data.join("frontend.log")).map_err(|_|"Не удалось открыть журнал запуска")?;
 let child=command(root.join("runtime/node.exe")).arg(root.join("scripts/serve-web.mjs")).env("DEBUGYCH_WEB_PORT",port.to_string()).env("DEBUGYCH_API_URL",&c.api_url).env("DEBUGYCH_ALLOW_REMOTE_API",if c.mode=="remote"{"1"}else{"0"}).stdout(Stdio::null()).stderr(log).spawn().map_err(|_|"В комплекте отсутствует runtime/node.exe. Распакуйте приложение полностью.")?;
 *state.web.lock().unwrap()=Some(child);let address=format!("http://127.0.0.1:{port}/");
 let deadline=Instant::now()+Duration::from_secs(15);while !client.get(&address).send().map_or(false,|r|r.status().is_success()){if Instant::now()>deadline{return Err("Не удалось открыть встроенный frontend. Проверьте комплект ресурсов и frontend.log.".into())}std::thread::sleep(Duration::from_millis(200));}
 app.get_webview_window("main").ok_or("Окно недоступно")?.navigate(address.parse().unwrap()).map_err(|_|"Не удалось открыть рабочую область")?;Ok(())
}
#[tauri::command]async fn start_application(app:tauri::AppHandle)->Result<(),String>{let state=app.state::<Runtime>();{let mut b=state.busy.lock().unwrap();if *b{return Err("Запуск уже выполняется".into())}*b=true;}let copy=app.clone();let result=tauri::async_runtime::spawn_blocking(move||boot(&copy)).await.map_err(|_|"Ошибка запуска приложения".to_string()).and_then(|r|r);if let Err(ref error)=result{*app.state::<Runtime>().status.lock().unwrap()=error.clone();}*app.state::<Runtime>().busy.lock().unwrap()=false;result}
fn main(){
 let app=tauri::Builder::default().plugin(tauri_plugin_single_instance::init(|app,_,_|{if let Some(w)=app.get_webview_window("main"){let _=w.show();let _=w.set_focus();}}))
 .setup(|app|{let path=config_path(app.handle()).unwrap();let cfg=fs::read(path).ok().and_then(|b|serde_json::from_slice::<Config>(&b).ok()).filter(valid).unwrap_or_default();app.manage(Runtime{config:Mutex::new(cfg),status:Mutex::new(String::new()),busy:Mutex::new(false),web:Mutex::new(None),wsl:Mutex::new(None)});let connection=MenuItem::with_id(app,"connection","Подключение",true,None::<&str>)?;let quit=MenuItem::with_id(app,"quit","Выход",true,None::<&str>)?;app.set_menu(Menu::with_items(app,&[&connection,&quit])?)?;Ok(())})
 .on_menu_event(|app,event|match event.id().as_ref(){"connection"=>{if let Some(w)=app.get_webview_window("main"){let _=w.navigate("http://tauri.localhost/index.html?settings=1".parse().unwrap());}},"quit"=>app.exit(0),_=>{}})
 .invoke_handler(tauri::generate_handler![get_config,startup_status,save_config,start_application]).build(tauri::generate_context!()).expect("Debugych startup");
 app.run(|app,event|{if matches!(event,tauri::RunEvent::Exit){let state=app.state::<Runtime>();for slot in [&state.web,&state.wsl]{if let Some(mut c)=slot.lock().unwrap().take(){drop(c.stdin.take());let _=c.kill();let _=c.wait();}}}});
}
#[cfg(test)]mod tests{use super::*;#[test]fn endpoints_do_not_accept_keys_cleartext_remote_or_local_paths(){assert!(valid(&Config::default()));for u in ["http://example.com","https://user:secret@example.com","https://example.com/api","https://example.com/#key"]{assert!(!valid(&Config{mode:"remote".into(),api_url:u.into(),backend_root:String::new()}));}assert!(valid(&Config{mode:"remote".into(),api_url:"https://example.com".into(),backend_root:String::new()}));}}
