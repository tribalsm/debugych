//! Read-only readiness. No provider completion, installation, or sandbox execution.
use serde::Serialize;
use serde_json::Value;
#[derive(Serialize)]
pub struct Check {pub name:String,pub status:String,pub detail:String}
fn check(name:&str,ok:bool,yes:&str,no:&str)->Check{Check{name:name.into(),status:if ok{"pass"}else{"fail"}.into(),detail:if ok{yes}else{no}.into()}}
pub fn health_checks(h:Option<&Value>)->Vec<Check>{
 let empty=Value::Null;let h=h.unwrap_or(&empty);
 vec![check("API",h["status"]=="ok","Backend отвечает","Backend недоступен: проверьте адрес, соединение и журнал запуска"),
 check("Linux runner / gVisor",h["execution"]=="gvisor-python"&&h["sandbox_available"]==true,"Backend подтвердил доступность изолированного runner","Runner недоступен. Требуется настроенное Linux-окружение с gVisor"),
 check("Playwright",h["playwright_available"]==true,"Образ Playwright доступен runner","Backend не подтвердил готовность Playwright"),
 Check{name:"AI-провайдер".into(),status:"warning".into(),detail:if h["ai_available"]==true&&h["ai_provider_mode"]=="live"{"Live-провайдер настроен. Доступность внешнего API и баланс не проверялись: платных запросов не выполнялось"}else{"Live AI не настроен или используется контрактный провайдер. Сохранённые результаты доступны без ключа"}.into()}]
}
pub fn run(config:&super::Config,folder:&std::path::Path)->Vec<Check>{
 let mut results=vec![check("Конфигурация",super::valid(config),"Адрес соответствует выбранному режиму","Local требует loopback HTTP, Remote требует HTTPS без ключей и пути")];
 if !super::valid(config){return results}
 let client=reqwest::blocking::Client::builder().timeout(std::time::Duration::from_secs(5)).redirect(reqwest::redirect::Policy::none()).no_proxy().build();
 let health=client.ok().and_then(|c|c.get(format!("{}/api/health",config.api_url.trim_end_matches('/'))).send().ok()).filter(|r|r.status().is_success()).and_then(|r|r.json::<Value>().ok());
 results.extend(health_checks(health.as_ref()));
 if config.mode=="remote"{results.push(Check{name:"WSL / Docker на Windows".into(),status:"not_applicable".into(),detail:"Remote Mode: локальные службы не запускаются и не проверяются. Runner находится на сервере".into()});return results}
 // Bounded read-only probe of the actual bootstrap distribution. The job owns only this probe.
 let path=folder.join(format!("docker-diagnostic-{}.txt",std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap_or_default().as_nanos()));let _=std::fs::create_dir_all(folder);
 let output=std::fs::File::create(&path);
 let mut ok=false;
 if let Ok(output)=output{let native=std::env::var_os("PATH").is_some_and(|p|std::env::split_paths(&p).any(|dir|dir.join("docker.exe").is_file()));let mut command=super::command(if native{"docker.exe"}else{"wsl.exe"});if native{command.args(["info","--format","{{.OSType}} {{json .Runtimes}}"]);}else{command.args(["-d","Ubuntu","-u","root","--","sh","-c","timeout 5 docker info --format '{{.OSType}} {{json .Runtimes}}'"]);}command.stdout(output).stderr(std::process::Stdio::null());let command=super::OwnedChild::spawn(&mut command);
 // A probe must never leave a WSL launcher running indefinitely.
 if let Ok(mut child)=command{let deadline=std::time::Instant::now()+std::time::Duration::from_secs(8);loop{match child.try_wait(){Ok(Some(s))=>{ok=s.success();break},Err(_)=>break,_=>{}}if std::time::Instant::now()>deadline{drop(child);break}std::thread::sleep(std::time::Duration::from_millis(60));}}}
 let text=std::fs::read_to_string(&path).unwrap_or_default();let _=std::fs::remove_file(path);
 results.push(Check{name:"Linux Docker / runsc".into(),status:if ok&&text.contains("linux")&&text.contains("runsc"){"pass"}else{"warning"}.into(),detail:if ok&&text.contains("linux")&&text.contains("runsc"){ "Docker отвечает, runtime runsc зарегистрирован. Это проверка конфигурации, а не запуск теста" }else{ "Автозапуск не готов: Linux Docker/runsc недоступен (Docker CLI или WSL Ubuntu). Уже доступный API может использовать отдельный настроенный runner" }.into()});results
}
#[cfg(test)]mod tests{use super::*;
 #[test]fn missing_backend_is_not_ready(){let c=health_checks(None);assert_eq!(c[0].status,"fail");assert_eq!(c[1].status,"fail");}
 #[test]fn ai_configuration_never_claims_paid_connectivity(){let h=serde_json::json!({"status":"ok","execution":"gvisor-python","sandbox_available":true,"playwright_available":true,"ai_available":true,"ai_provider_mode":"live"});let c=health_checks(Some(&h));assert_eq!(c[1].status,"pass");assert_eq!(c[3].status,"warning");assert!(c[3].detail.contains("не проверялись"));}
 #[test]fn configured_sandbox_is_not_available_sandbox(){let h=serde_json::json!({"status":"ok","sandbox_configured":true,"execution":"trusted-demo-only","sandbox_available":false});assert_eq!(health_checks(Some(&h))[1].status,"fail");}
}
