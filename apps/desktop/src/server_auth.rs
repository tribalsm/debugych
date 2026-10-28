//! An origin-scoped Windows Credential Manager entry shared by both windows.
//! Never return a credential through IPC, config JSON or logs.
pub fn token_valid(token:&str)->bool{(43..=256).contains(&token.len())&&token.bytes().all(|b|b.is_ascii_alphanumeric()||b==b'-'||b==b'_')}
pub fn valid_route(route:&str)->bool{route.is_empty()||route.parse::<std::net::Ipv4Addr>().is_ok_and(|ip|ip.is_private())}
fn route_address(origin:&str,route:&str)->Result<Option<(String,std::net::SocketAddr)>,String>{
 if route.is_empty(){return Ok(None)}if !valid_route(route){return Err("Only a private VPN IPv4 route is allowed".into())}let url=reqwest::Url::parse(origin).map_err(|_|"Invalid server origin")?;if url.scheme()!="https"{return Err("VPN route requires HTTPS".into())}let host=url.host_str().ok_or("Missing HTTPS hostname")?.to_owned();let ip=route.parse::<std::net::IpAddr>().map_err(|_|"Invalid VPN address")?;Ok(Some((host,std::net::SocketAddr::new(ip,url.port_or_known_default().unwrap_or(443)))))
}
pub fn blocking_client(origin:&str,route:&str,seconds:u64)->Result<reqwest::blocking::Client,String>{let mut builder=reqwest::blocking::Client::builder().timeout(std::time::Duration::from_secs(seconds)).redirect(reqwest::redirect::Policy::none()).no_proxy();if let Some((host,address))=route_address(origin,route)?{builder=builder.resolve(&host,address)}builder.build().map_err(|_|"HTTPS transport unavailable".into())}
pub fn async_client(origin:&str,route:&str)->Result<reqwest::Client,String>{let mut builder=reqwest::Client::builder().timeout(std::time::Duration::from_secs(8)).connect_timeout(std::time::Duration::from_secs(3)).redirect(reqwest::redirect::Policy::none()).no_proxy();if let Some((host,address))=route_address(origin,route)?{builder=builder.resolve(&host,address)}builder.build().map_err(|_|"HTTPS transport unavailable".into())}
fn target(origin:&str)->Result<Vec<u16>,String>{let u=reqwest::Url::parse(origin).map_err(|_|"Invalid HTTPS origin")?;if u.scheme()!="https"||u.host_str().is_none()||!u.username().is_empty()||u.password().is_some()||u.query().is_some()||u.fragment().is_some()||u.path()!="/"{return Err("Server credentials require an HTTPS origin".into())}Ok(format!("Debugych.Server.{}\0",u.origin().ascii_serialization()).encode_utf16().collect())}
#[cfg(windows)]pub fn load(origin:&str)->Result<Option<String>,String>{
 if reqwest::Url::parse(origin).map_or(true,|u|u.scheme()!="https"){return Ok(None)}let name=target(origin)?;use windows_sys::Win32::{Security::Credentials::*,Foundation::GetLastError};
 unsafe{let mut credential=std::ptr::null_mut();if CredReadW(name.as_ptr(),CRED_TYPE_GENERIC,0,&mut credential)==0{return if GetLastError()==1168{Ok(None)}else{Err("Windows credential store unavailable".into())}}
 let size=(*credential).CredentialBlobSize as usize;let result=if (43..=256).contains(&size)&&!(*credential).CredentialBlob.is_null(){String::from_utf8(std::slice::from_raw_parts((*credential).CredentialBlob,size).to_vec()).ok().filter(|s|token_valid(s))}else{None};CredFree(credential as _);result.map(Some).ok_or("Invalid stored credential".into())}
}
#[cfg(windows)]pub fn store(origin:&str,token:&str)->Result<(),String>{
 let mut name=target(origin)?;if !token_valid(token){return Err("Token must contain 43..256 URL-safe characters".into())}use windows_sys::Win32::Security::Credentials::*;
 let mut user:Vec<u16>="Debugych owner\0".encode_utf16().collect();let mut bytes=token.as_bytes().to_vec();let mut credential=CREDENTIALW::default();credential.Type=CRED_TYPE_GENERIC;credential.TargetName=name.as_mut_ptr();credential.UserName=user.as_mut_ptr();credential.CredentialBlobSize=bytes.len()as u32;credential.CredentialBlob=bytes.as_mut_ptr();credential.Persist=CRED_PERSIST_LOCAL_MACHINE;
 let ok=unsafe{CredWriteW(&credential,0)}!=0;bytes.fill(0);if ok{Ok(())}else{Err("Unable to save Windows credential".into())}
}
#[cfg(windows)]pub fn remove(origin:&str)->Result<(),String>{let name=target(origin)?;use windows_sys::Win32::{Security::Credentials::*,Foundation::GetLastError};if unsafe{CredDeleteW(name.as_ptr(),CRED_TYPE_GENERIC,0)}!=0||unsafe{GetLastError()}==1168{Ok(())}else{Err("Unable to remove Windows credential".into())}}
#[cfg(not(windows))]pub fn load(_origin:&str)->Result<Option<String>,String>{Ok(None)}
#[cfg(not(windows))]pub fn store(_origin:&str,_token:&str)->Result<(),String>{Err("Windows Credential Manager required".into())}
#[cfg(not(windows))]pub fn remove(_origin:&str)->Result<(),String>{Err("Windows Credential Manager required".into())}
pub fn blocking(client:&reqwest::blocking::Client,url:&str,origin:&str)->Result<reqwest::blocking::RequestBuilder,String>{let request=client.get(url);Ok(if let Some(token)=load(origin)?{request.bearer_auth(token)}else{request})}
pub fn asynchronous(request:reqwest::RequestBuilder,origin:&str)->Result<reqwest::RequestBuilder,String>{Ok(if let Some(token)=load(origin)?{request.bearer_auth(token)}else{request})}
#[tauri::command]pub fn set_server_token(window:tauri::Window,app:tauri::AppHandle,api_url:String,token:String)->Result<(),String>{
 use tauri::Manager;if window.label()!="main"{return Err("Use main connection settings".into())}let state=app.state::<crate::Runtime>();if *state.busy.lock().unwrap(){return Err("Startup is in progress".into())}if token.is_empty(){remove(&api_url)?}else{store(&api_url,&token)?}state.web.lock().unwrap().take();state.frontend.lock().unwrap().clear();app.state::<crate::backend::Backend>().cancel_all();Ok(())
}
#[tauri::command]pub fn server_token_configured(api_url:String)->Result<bool,String>{Ok(load(&api_url)?.is_some())}
#[cfg(test)]mod tests{use super::*;
 #[test]fn secrets_are_bound_to_https_origin(){assert!(target("https://one.example").is_ok());assert_ne!(target("https://one.example").unwrap(),target("https://two.example").unwrap());for s in ["http://example.com","https://user:key@example.com","https://example.com/path","https://example.com/?token=x"]{assert!(target(s).is_err())}}
 #[test]fn header_injection_and_weak_tokens_are_rejected(){assert!(token_valid(&"A".repeat(64)));for t in ["short".into(),format!("{}\r\nX: y","A".repeat(64)),"A".repeat(257)]{assert!(!token_valid(&t))}}
 #[test]fn vpn_routing_preserves_origin_and_refuses_unsafe_targets(){let route=route_address("https://api.example:9443","10.66.66.1").unwrap().unwrap();assert_eq!(route.0,"api.example");assert_eq!(route.1.port(),9443);for ip in ["127.0.0.1","0.0.0.0","169.254.169.254","8.8.8.8","bad"]{assert!(!valid_route(ip))}assert!(route_address("http://api.example","10.66.66.1").is_err())}
 #[cfg(windows)]#[test]fn credential_store_roundtrip_and_removal(){let origin=format!("https://credential-test-{}.invalid",std::process::id());store(&origin,&"Q".repeat(64)).unwrap();assert_eq!(load(&origin).unwrap().unwrap(),"Q".repeat(64));remove(&origin).unwrap();assert!(load(&origin).unwrap().is_none())}
}
