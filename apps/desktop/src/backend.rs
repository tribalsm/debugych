use std::{collections::HashMap,path::PathBuf,sync::Mutex,time::Duration};
use serde::{Deserialize,Serialize};
use futures_util::future::{AbortHandle,Abortable};
use tauri::{State,Manager,Emitter};
#[derive(Clone,Debug,Serialize,Deserialize)]
#[serde(default,rename_all="camelCase")]
pub struct Config {pub backend_url:String,pub frontend_url:String,pub project_id:String,pub run_id:String,pub enabled:bool,pub notifications:bool,pub phrases:bool,#[serde(rename="contextualAIEnabled",alias="contextualAiEnabled")]pub contextual_ai_enabled:bool}
impl Default for Config {fn default()->Self{Self{backend_url:"http://127.0.0.1:8000".into(),frontend_url:"http://127.0.0.1:5173".into(),project_id:String::new(),run_id:String::new(),enabled:true,notifications:true,phrases:true,contextual_ai_enabled:false}}}
#[derive(Clone,Default,Serialize,Deserialize)]
pub struct Saved {pub config:Config,#[serde(default)]pub seen:Vec<String>}
pub struct Backend {saved:Mutex<Saved>,path:PathBuf,client:reqwest::Client,pending:Mutex<HashMap<String,AbortHandle>>,history_lock:Mutex<()>}
pub fn valid_id(id:&str)->bool{id.len()==36&&id.bytes().enumerate().all(|(i,c)|if [8,13,18,23].contains(&i){c==b'-'}else{c.is_ascii_hexdigit()})}
pub fn origin(value:&str)->Result<String,String>{
 if value.len()>2048{return Err("Адрес слишком длинный".into());}
 let u=reqwest::Url::parse(value).map_err(|_|"Некорректный адрес сервера")?;
 if !["http","https"].contains(&u.scheme())||u.host_str().is_none()||!u.username().is_empty()||u.password().is_some()||u.query().is_some()||u.fragment().is_some()||u.path()!="/"{return Err("Нужен http(s) адрес без пути, параметров или логина".into());}
 Ok(u.origin().ascii_serialization())
}
pub fn allowed_path(path:&str)->bool {
 if ["/api/health","/api/projects","/api/companion/status"].contains(&path){return true;}
 if let Some(id)=path.strip_prefix("/api/bugs?project_id="){return valid_id(id);}
 let parts:Vec<_>=path.split('/').collect();
 parts.len()==5&&parts[1]=="api"&&parts[2]=="projects"&&valid_id(parts[3])&&["runs","fixes","test-cases","requirements"].contains(&parts[4])
}
impl Backend {
 pub fn load(path:PathBuf)->Result<Self,Box<dyn std::error::Error>>{
  let mut saved:Saved=std::fs::read(&path).ok().and_then(|s|serde_json::from_slice(&s).ok()).unwrap_or_default();
  if origin(&saved.config.backend_url).is_err()||origin(&saved.config.frontend_url).is_err(){saved=Saved::default();}
  saved.seen=saved.seen.into_iter().filter(|s|s.len()<256).rev().take(128).collect();saved.seen.reverse();
  Ok(Self{saved:Mutex::new(saved),path,client:reqwest::Client::builder().timeout(Duration::from_secs(8)).connect_timeout(Duration::from_secs(3)).redirect(reqwest::redirect::Policy::none()).no_proxy().build()?,pending:Mutex::new(HashMap::new()),history_lock:Mutex::new(())})
 }
 fn save(&self,saved:&Saved)->Result<(),String>{if let Some(parent)=self.path.parent(){std::fs::create_dir_all(parent).map_err(|e|e.to_string())?;}let tmp=self.path.with_extension("json.tmp");std::fs::write(&tmp,persisted_settings(saved)?).map_err(|e|e.to_string())?;std::fs::rename(tmp,&self.path).map_err(|e|e.to_string())}
 pub fn set_context(&self,backend:&str,frontend:&str,project:&str){
  let mut saved=self.saved.lock().unwrap();let changed=saved.config.backend_url!=backend||saved.config.project_id!=project;
  saved.config.backend_url=backend.into();saved.config.frontend_url=if frontend.is_empty(){"http://127.0.0.1:8000".into()}else{frontend.into()};saved.config.project_id=project.into();if changed{saved.config.run_id.clear();}drop(saved);if changed{self.cancel_all();}
 }
 pub fn cancel_all(&self){for handle in self.pending.lock().unwrap().values(){handle.abort();}}
}
#[tauri::command]
pub fn get_companion_settings(state:State<'_,Backend>)->Saved{state.saved.lock().unwrap().clone()}
// Connection and project live only in Desktop connection.json, never in a second pet configuration.
fn persisted_settings(saved:&Saved)->Result<Vec<u8>,String>{let mut value=serde_json::to_value(saved).map_err(|_|"Настройки недоступны")?;if let Some(c)=value["config"].as_object_mut(){for key in ["backendUrl","frontendUrl","projectId"]{c.remove(key);}}serde_json::to_vec(&value).map_err(|_|"Настройки недоступны".into())}
#[tauri::command]
pub fn save_companion_config(app:tauri::AppHandle,state:State<'_,Backend>,mut config:Config,revision:u64)->Result<(),String>{
 config.backend_url=origin(&config.backend_url)?;config.frontend_url=origin(&config.frontend_url)?;let shared=crate::context(&app);
 if config.backend_url!=shared.backend_url||(!shared.frontend_url.is_empty()&&config.frontend_url!=shared.frontend_url){return Err("Подключение общее для двух окон. Измените его в главном окне.".into())}
 if !config.run_id.is_empty()&&!valid_id(&config.run_id){return Err("Некорректный запуск".into())}
 if !config.project_id.is_empty()&&!valid_id(&config.project_id){return Err("Некорректный проект".into())}
 let runtime=app.state::<crate::Runtime>();let _gate=runtime.context_gate.lock().unwrap();let mut central=runtime.config.lock().unwrap();
 if central.revision!=revision{return Err("Контекст изменился. Повторите действие.".into())}
 if config.backend_url!=central.api_url.trim_end_matches('/'){return Err("Подключение изменилось".into())}
 let mut next_c=central.clone();next_c.project_id=config.project_id.clone();next_c.revision+=1;
 let mut saved=state.saved.lock().unwrap();let changed=saved.config.enabled!=config.enabled||saved.config.project_id!=config.project_id;
 let mut next=saved.clone();next.config=config;state.save(&next)?;crate::persist(&app,&next_c)?;*saved=next;*central=next_c;drop(saved);drop(central);if changed{state.cancel_all();}crate::broadcast_context(&app);Ok(())
}
#[tauri::command]
pub fn save_companion_seen(state:State<'_,Backend>,keys:Vec<String>)->Result<(),String>{if keys.len()>128||keys.iter().any(|s|s.len()>256){return Err("Некорректная история".into());}let mut saved=state.saved.lock().unwrap();saved.seen=keys;state.save(&saved)}
#[tauri::command]
pub fn cancel_backend_read(state:State<'_,Backend>,request_id:String){if let Some(handle)=state.pending.lock().unwrap().get(&request_id){handle.abort();}}
#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub struct Reply {status:u16,data:serde_json::Value}
#[tauri::command]
pub async fn backend_get(state:State<'_,Backend>,path:String,request_id:String)->Result<Reply,String>{
 if !allowed_path(&path)||!valid_id(&request_id){return Err("Запрос вне разрешённого read-only API".into());}
 let config=state.saved.lock().unwrap().config.clone();if!config.enabled{return Err("Подключение отключено".into());}
 let (handle,registration)=AbortHandle::new_pair();{
  let mut pending=state.pending.lock().unwrap();if pending.len()>=8||pending.contains_key(&request_id){return Err("Слишком много запросов".into());}pending.insert(request_id.clone(),handle);
 }
 let result=Abortable::new(async{
  let current=state.saved.lock().unwrap().config.clone();if current.backend_url!=config.backend_url||current.project_id!=config.project_id{return Err("Контекст изменился".into());}
  let mut response=state.client.get(format!("{}{}",origin(&config.backend_url)?,path)).header("Accept","application/json").send().await.map_err(|_|"Backend недоступен".to_string())?;
  let status=response.status().as_u16();let mut bytes=Vec::new();
  while let Some(chunk)=response.chunk().await.map_err(|_|"Ответ backend прерван".to_string())?{if bytes.len()+chunk.len()>4*1024*1024{return Err("Ответ API превышает 4 MiB".into());}bytes.extend_from_slice(&chunk);}
  let data=if status==200{serde_json::from_slice(&bytes).map_err(|_|"Backend вернул не JSON".to_string())?}else{serde_json::Value::Null};
  Ok(Reply{status,data})
 },registration).await;
 state.pending.lock().unwrap().remove(&request_id);result.map_err(|_|"Запрос отменён".to_string())?
}
#[derive(Deserialize)]
#[serde(rename_all="snake_case")]
pub enum Page {Project,Proof,Tests,Diff,Verification,Results}
pub fn allowed_chat_post(path:&str)->bool{["/api/companion/preview","/api/companion/ask"].contains(&path)}
#[tauri::command]
pub async fn companion_post(state:State<'_,Backend>,path:String,body:serde_json::Value,request_id:String)->Result<Reply,String>{
 if!allowed_chat_post(&path)||!valid_id(&request_id)||serde_json::to_vec(&body).map_err(|_|"Неверный запрос")?.len()>16000{return Err("Запрос вне API объяснений".into());}
 let config=state.saved.lock().unwrap().config.clone();if!config.enabled||!config.contextual_ai_enabled{return Err("AI-ответы выключены".into());}
 let(handle,registration)=AbortHandle::new_pair();{let mut p=state.pending.lock().unwrap();if p.len()>=8||p.contains_key(&request_id){return Err("Слишком много запросов".into());}p.insert(request_id.clone(),handle);}
 let result=Abortable::new(async{let current=state.saved.lock().unwrap().config.clone();if current.backend_url!=config.backend_url||current.project_id!=config.project_id{return Err("Контекст изменился".into());}let mut response=state.client.post(format!("{}{}",origin(&config.backend_url)?,path)).timeout(Duration::from_secs(65)).json(&body).send().await.map_err(|e|if e.is_timeout(){"AI_TIMEOUT"}else{"AI_UNAVAILABLE"})?;let status=response.status().as_u16();let mut bytes=Vec::new();while let Some(chunk)=response.chunk().await.map_err(|_|"Ответ прерван")?{if bytes.len()+chunk.len()>1024*1024{return Err("Ответ слишком велик".into());}bytes.extend_from_slice(&chunk);}let data=serde_json::from_slice(&bytes).map_err(|_|"AI_INVALID_RESPONSE")?;Ok(Reply{status,data})},registration).await;
 state.pending.lock().unwrap().remove(&request_id);result.map_err(|_|"Запрос отменён".to_string())?
}
pub fn valid_history(history:&serde_json::Value)->bool{let Some(rows)=history.as_array()else{return false;};if rows.len()>5{return false;}for row in rows{let Some(scope)=row["scope"].as_str()else{return false;};let parts:Vec<_>=scope.split('|').collect();if parts.len()!=3||origin(parts[0]).is_err()||!valid_id(parts[1])||(parts[2]!="empty"&&!valid_id(parts[2])){return false;}let Some(messages)=row["messages"].as_array()else{return false;};if messages.len()>24{return false;}for m in messages{if!matches!(m["role"].as_str(),Some("user"|"assistant"))||m["text"].as_str().map_or(true,|s|s.len()>16000)||m["scope"].as_str()!=Some(scope){return false;}}}true}
#[tauri::command]
pub fn get_chat_history(state:State<'_,Backend>)->serde_json::Value{let _guard=state.history_lock.lock().unwrap();let path=state.path.with_file_name("chat-history.json");if std::fs::metadata(&path).map_or(false,|m|m.len()<=65536){if let Ok(bytes)=std::fs::read(path){if let Ok(v)=serde_json::from_slice::<serde_json::Value>(&bytes){if valid_history(&v["history"]){return v;}}}}serde_json::json!({"enabled":false,"history":[]})}
#[tauri::command]
pub fn save_chat_history(state:State<'_,Backend>,enabled:bool,history:serde_json::Value)->Result<(),String>{let _guard=state.history_lock.lock().unwrap();let rows=if enabled{history}else{serde_json::json!([])};if!valid_history(&rows){return Err("Некорректная история".into());}let bytes=serde_json::to_vec(&serde_json::json!({"enabled":enabled,"history":rows})).map_err(|_|"История недоступна")?;if bytes.len()>65536{return Err("История превышает 64 KiB".into());}let path=state.path.with_file_name("chat-history.json");if let Some(parent)=path.parent(){std::fs::create_dir_all(parent).map_err(|_|"Настройки недоступны")?;}let tmp=path.with_extension("tmp");std::fs::write(&tmp,bytes).map_err(|_|"История не сохранена")?;std::fs::rename(tmp,path).map_err(|_|"История не сохранена".to_string())}
#[derive(Default,Deserialize)]
#[serde(default,rename_all="camelCase",deny_unknown_fields)]
pub struct Target {pub bug_id:Option<String>,pub fix_id:Option<String>,pub run_id:Option<String>}
pub fn result_url(frontend:&str,page:Page,project:&str,target:&Target)->Result<String,String>{
 if!valid_id(project){return Err("Выберите корректный проект".into());}
 for id in [&target.bug_id,&target.fix_id,&target.run_id].into_iter().flatten(){if!valid_id(id){return Err("Некорректная ссылка на результат".into());}}
 let route=match page{Page::Project=>"overview",Page::Tests=>"tests",Page::Results=>"report",Page::Proof|Page::Diff|Page::Verification=>"bugs"};
 let mut url=format!("{}/#/workspace/{}?project={}",origin(frontend)?,route,project);
 if let Some(id)=&target.bug_id{url.push_str(&format!("&bug={id}"));}if let Some(id)=&target.fix_id{url.push_str(&format!("&fix={id}"));}if let Some(id)=&target.run_id{url.push_str(&format!("&run={id}"));}
 let section=match page{Page::Proof=>Some("proof"),Page::Diff=>Some("diff"),Page::Verification=>Some("verification"),_=>None};if let Some(s)=section{url.push_str(&format!("&section={s}"));}Ok(url)
}
pub fn page_url(frontend:&str,page:Page,project:&str)->Result<String,String>{result_url(frontend,page,project,&Target::default())}
#[tauri::command]
pub fn open_companion_page(app:tauri::AppHandle,page:Page,project_id:String,target:Option<Target>)->Result<(),String>{
 let c=crate::context(&app);if c.project_id!=project_id{return Err("Выбран другой проект. Обновите результат.".into())}crate::restore_main(&app)?;
 if c.frontend_url.is_empty(){return Err("Основное приложение ещё подключается".into())}
 let url=result_url(&c.frontend_url,page,&project_id,&target.unwrap_or_default())?;let hash=url.split_once('#').ok_or("Некорректный маршрут")?.1;
 app.emit_to("main","desktop-navigate",hash).map_err(|_|"Не удалось открыть результат в приложении".into())
}
#[cfg(test)]mod tests{
 use super::*;
 #[test]fn ai_setting_matches_the_frontend_acronym_and_preserves_legacy_settings(){let current:Config=serde_json::from_value(serde_json::json!({"contextualAIEnabled":true})).unwrap();assert!(current.contextual_ai_enabled);let saved=serde_json::to_value(current).unwrap();assert_eq!(saved["contextualAIEnabled"],true);assert!(saved.get("contextualAiEnabled").is_none());let legacy:Config=serde_json::from_value(serde_json::json!({"contextualAiEnabled":true})).unwrap();assert!(legacy.contextual_ai_enabled);assert!(!serde_json::from_value::<Config>(serde_json::json!({})).unwrap().contextual_ai_enabled);}
 #[test]fn chat_posts_are_explicit_and_ai_defaults_off(){assert!(allowed_chat_post("/api/companion/preview"));assert!(allowed_chat_post("/api/companion/ask"));for p in ["/api/companion/ask?key=x","https://evil.test","/api/fixes/apply","/api/projects/x/analyze"]{assert!(!allowed_chat_post(p));}assert!(!Config::default().contextual_ai_enabled);}
 #[test]fn bounded_history_requires_project_run_scope(){let scope="http://127.0.0.1:8000|4552f6ba-cd41-48d4-a947-39e3b58314ac|8a148635-63fd-42c8-8319-95f8d0255183";let h=serde_json::json!([{"scope":scope,"messages":[{"role":"user","text":"question","scope":scope}]}]);assert!(valid_history(&h));let mut foreign=h.clone();foreign[0]["messages"][0]["scope"]=serde_json::json!("other");assert!(!valid_history(&foreign));let mut huge=h.clone();huge[0]["messages"][0]["text"]=serde_json::json!("x".repeat(16001));assert!(!valid_history(&huge));assert!(!valid_history(&serde_json::json!({})));}

 #[test]fn exact_results_are_addressed_without_accepting_injected_urls(){
  let project="4552f6ba-cd41-48d4-a947-39e3b58314ac";let target=Target{bug_id:Some("45a3e289-39c2-4bcd-b504-5e1ec62cb394".into()),fix_id:Some("c41ceb12-55b9-4d85-87a3-332eba94717e".into()),run_id:Some("55e90faa-d947-4001-ba83-a7ecaf63b540".into())};
  let url=result_url("http://127.0.0.1:5173",Page::Verification,project,&target).unwrap();assert!(url.contains("&section=verification"));assert!(url.contains("&fix=c41ceb12-55b9-4d85-87a3-332eba94717e"));assert!(url.contains("&run=55e90faa-d947-4001-ba83-a7ecaf63b540"));
  assert!(result_url("http://localhost",Page::Diff,project,&Target{bug_id:Some("x&run=evil".into()),..Target::default()}).is_err());
 }
 #[test]fn only_existing_read_only_routes_are_allowed(){let id="024f84b2-6cc8-49dc-87a1-e0c5c35b63eb";assert!(allowed_path(&format!("/api/projects/{id}/runs")));assert!(allowed_path(&format!("/api/bugs?project_id={id}")));for path in ["/api/projects/../runs","/api/ai/status","/api/projects/x/analyze","http://evil.test","/api/projects?token=secret"]{assert!(!allowed_path(path));}}
 #[test]fn urls_have_no_credentials_or_script_routes(){for url in ["file:///c:/x","javascript:alert(1)","https://a:b@example.com","http://localhost/api","http://localhost/?x=y"]{assert!(origin(url).is_err());}assert_eq!(origin("http://127.0.0.1:8000").unwrap(),"http://127.0.0.1:8000");assert!(page_url("https://example.com",Page::Proof,"../../etc").is_err());assert!(page_url("https://example.com",Page::Diff,"024f84b2-6cc8-49dc-87a1-e0c5c35b63eb").unwrap().contains("#/workspace/bugs?project="));}
}

#[cfg(test)]mod desktop_tests{use super::*;
 #[test]fn disk_settings_do_not_duplicate_connection_or_project(){let saved=Saved::default();let v:serde_json::Value=serde_json::from_slice(&persisted_settings(&saved).unwrap()).unwrap();for k in ["backendUrl","frontendUrl","projectId"]{assert!(v["config"].get(k).is_none());}assert_eq!(v["config"]["contextualAIEnabled"],false);assert!(serde_json::to_value(saved).unwrap()["config"].get("backendUrl").is_some());}
 #[test]fn all_result_types_keep_their_exact_route(){let p="4552f6ba-cd41-48d4-a947-39e3b58314ac";for (page,section) in [(Page::Proof,"proof"),(Page::Diff,"diff"),(Page::Verification,"verification")]{let url=result_url("http://127.0.0.1:50400",page,p,&Target::default()).unwrap();assert!(url.starts_with("http://127.0.0.1:50400/#/workspace/bugs?project="));assert!(url.ends_with(section));}}
}
