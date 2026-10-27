//! Identify old releases by their full executable path and adjacent release manifest.
//! Never terminate a process discovered here.
use std::path::Path;
pub fn is_legacy(path:&Path)->bool{
 let Some(parent)=path.parent()else{return false};
 let manifest=parent.join("build.json");
 if !manifest.metadata().is_ok_and(|m|m.len()<=32768){return false}
 let value=std::fs::read(manifest).ok().and_then(|b|serde_json::from_slice::<serde_json::Value>(&b).ok());
 value.is_some_and(|v|matches!(v["version"].as_str(),Some("1.0.0"|"1.1.0"))&&v["runtime"].as_str().is_some_and(|s|s.contains("Tauri 2")))
}
#[cfg(windows)]pub fn conflicts()->Vec<String>{
 use windows_sys::Win32::{Foundation::{CloseHandle,INVALID_HANDLE_VALUE},System::{Diagnostics::ToolHelp::*,Threading::*}};
 let mut found=Vec::new();unsafe{
 let snapshot=CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS,0);if snapshot==INVALID_HANDLE_VALUE{return found}
 let mut entry:PROCESSENTRY32W=std::mem::zeroed();entry.dwSize=std::mem::size_of_val(&entry)as u32;
 let mut next=Process32FirstW(snapshot,&mut entry);
 while next!=0{if entry.th32ProcessID!=std::process::id(){let process=OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION,0,entry.th32ProcessID);if !process.is_null(){let mut buf=vec![0u16;32768];let mut length=buf.len()as u32;if QueryFullProcessImageNameW(process,0,buf.as_mut_ptr(),&mut length)!=0{let path=String::from_utf16_lossy(&buf[..length as usize]);if is_legacy(Path::new(&path)){found.push(format!("PID {}: {}",entry.th32ProcessID,path));}}CloseHandle(process);}}next=Process32NextW(snapshot,&mut entry);}CloseHandle(snapshot);}found
}
#[cfg(not(windows))]pub fn conflicts()->Vec<String>{Vec::new()}
#[cfg(test)]mod tests{use super::*;
 #[test]fn name_alone_never_identifies_an_old_app(){assert!(!is_legacy(Path::new("C:/missing/Debugych.exe")));}
 #[test]fn release_manifest_distinguishes_legacy_and_current(){let dir=std::env::temp_dir().join(format!("debugych-legacy-test-{}",std::process::id()));std::fs::create_dir_all(&dir).unwrap();let p=dir.join("Debugych.exe");for(version,expected)in[("1.1.0",true),("1.2.0",false)]{std::fs::write(dir.join("build.json"),serde_json::json!({"version":version,"runtime":"Tauri 2 + Windows WebView2 + bundled Node"}).to_string()).unwrap();assert_eq!(is_legacy(&p),expected);}std::fs::remove_dir_all(dir).unwrap();}
}
