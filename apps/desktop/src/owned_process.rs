//! Own only child processes started by this application. Never stop shared Docker/WSL services.
use std::process::{Child,Command,ExitStatus};
pub struct OwnedChild { child:Child, #[cfg(windows)] job:Job }
#[cfg(windows)]struct Job(windows_sys::Win32::Foundation::HANDLE);
#[cfg(windows)]unsafe impl Send for Job {}
#[cfg(windows)]impl Drop for Job {fn drop(&mut self){unsafe{windows_sys::Win32::Foundation::CloseHandle(self.0);}}}
impl OwnedChild {
 pub fn spawn(command:&mut Command)->std::io::Result<Self>{
  let mut child=command.spawn()?;
  #[cfg(windows)] {
   use std::os::windows::io::AsRawHandle;
   use windows_sys::Win32::{Foundation::CloseHandle,System::JobObjects::*};
   let handle=unsafe{CreateJobObjectW(std::ptr::null(),std::ptr::null())};
   if handle.is_null(){let e=std::io::Error::last_os_error();let _=child.kill();let _=child.wait();return Err(e)}
   let mut limits:JOBOBJECT_EXTENDED_LIMIT_INFORMATION=unsafe{std::mem::zeroed()};limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
   let ok=unsafe{SetInformationJobObject(handle,JobObjectExtendedLimitInformation,&limits as *const _ as *const _,std::mem::size_of_val(&limits)as u32)!=0&&AssignProcessToJobObject(handle,child.as_raw_handle()as _)!=0};
   if !ok{let e=std::io::Error::last_os_error();unsafe{CloseHandle(handle);}let _=child.kill();let _=child.wait();return Err(e)}
   Ok(Self{child,job:Job(handle)})
  }
  #[cfg(not(windows))] {Ok(Self{child})}
 }
 pub fn stdin(&mut self)->Option<&mut std::process::ChildStdin>{self.child.stdin.as_mut()}
 pub fn try_wait(&mut self)->std::io::Result<Option<ExitStatus>>{self.child.try_wait()}
}
impl Drop for OwnedChild {fn drop(&mut self){let _=self.child.stdin.take();#[cfg(windows)]unsafe{windows_sys::Win32::System::JobObjects::TerminateJobObject(self.job.0,0);};let _=self.child.kill();let _=self.child.wait();}}
#[cfg(all(test,windows))]mod tests{
 use super::*;
 #[test]fn dropping_owner_terminates_its_actual_child(){
  use windows_sys::Win32::{Foundation::CloseHandle,System::Threading::*};
  let mut command=crate::command("cmd.exe");command.args(["/C","ping -n 30 127.0.0.1 >nul"]).stdout(std::process::Stdio::null()).stderr(std::process::Stdio::null());
  let child=OwnedChild::spawn(&mut command).unwrap();
  let handle=unsafe{OpenProcess(PROCESS_SYNCHRONIZE,0,child.child.id())};assert!(!handle.is_null());
  drop(child);assert_eq!(unsafe{WaitForSingleObject(handle,1000)},0);unsafe{CloseHandle(handle);}
 }
}
