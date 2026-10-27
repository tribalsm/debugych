use std::{sync::{Arc,atomic::{AtomicBool,Ordering}},thread,time::{Duration,Instant}};
mod preferences;
use crate::backend;
mod layout;
use layout::{Layout,Rect};
static WINDOW_LAYOUT:Mutex<Option<Layout>>=Mutex::new(None);
use preferences::{Anchor,Bounds,PreferenceStore};
use serde::{Deserialize,Serialize};
use std::sync::Mutex;
use tauri::{Emitter,Manager,LogicalSize,PhysicalPosition,State,WebviewWindow,WindowEvent};

#[derive(Clone)]
pub(crate) struct PetState { expanded:Arc<AtomicBool>, gesture:Arc<AtomicBool>, preferences:Arc<Mutex<PreferenceStore>>, ready:Arc<AtomicBool> }
#[derive(Deserialize)]
struct HitMask { cell:f64, columns:usize, rows:Vec<u32> }
impl HitMask {
    fn contains(&self,x:f64,y:f64)->bool {
        if x<0.0 || y<0.0 { return false; }
        let col=(x/self.cell).floor() as usize;
        let row=(y/self.cell).floor() as usize;
        col<self.columns && row<self.rows.len() && (self.rows[row] & (1u32<<col))!=0
    }
}
#[cfg(target_os="windows")]
fn left_button_down()->bool {
    #[link(name="user32")]
    unsafe extern "system" { fn GetAsyncKeyState(key:i32)->i16; }
    // Read only the left button state so native dragging never loses capture.
    unsafe { GetAsyncKeyState(1)<0 }
}
#[cfg(not(target_os="windows"))]
fn left_button_down()->bool { false }

#[cfg(target_os="windows")]
fn apply_hit_region(window:&WebviewWindow,expanded:bool)->tauri::Result<()> {
    use std::ffi::c_void;
    #[link(name="gdi32")]
    unsafe extern "system" {
        fn CreateRectRgn(left:i32,top:i32,right:i32,bottom:i32)->*mut c_void;
        fn CombineRgn(dest:*mut c_void,a:*mut c_void,b:*mut c_void,mode:i32)->i32;
        fn DeleteObject(object:*mut c_void)->i32;
    }
    #[link(name="user32")]
    unsafe extern "system" { fn SetWindowRgn(window:*mut c_void,region:*mut c_void,redraw:i32)->i32; }
    let size=window.inner_size()?;let hwnd=window.hwnd()?.0;
    let layout=*WINDOW_LAYOUT.lock().unwrap();
    let pet=layout.map(|l|l.pet).unwrap_or(Rect{x:0,y:0,width:size.width as i32,height:size.height as i32});
    let sx=pet.width as f64/224.0;let sy=pet.height as f64/270.0;
    // SetWindowRgn can emit another resize notification. Re-applying the same
    // region from that notification causes a native repaint loop even on pause.
    static LAST_REGION:Mutex<Option<(isize,u32,u32,bool,Option<Layout>)>>=Mutex::new(None);
    let key=(hwnd as isize,size.width,size.height,expanded,layout);
    if LAST_REGION.lock().unwrap().as_ref()==Some(&key){return Ok(());}
    let mask:HitMask=serde_json::from_str(include_str!("hit-mask.json"))?;
    unsafe {
        let region=CreateRectRgn(0,0,0,0);
        if region.is_null(){return Err(std::io::Error::last_os_error().into());}
        {
            let offset_x=pet.x as f64;let offset_y=pet.y as f64;
            // One-cell margin preserves the hover outline and all sampled poses.
            for row in 0..mask.rows.len() {
                let mut col=0;
                let covered=|r:usize,c:usize|->bool{(-1..=1).any(|dy|(-1..=1).any(|dx|mask.contains((c as f64+dx as f64+0.5)*mask.cell,(r as f64+dy as f64+0.5)*mask.cell)))};
                while col<mask.columns {
                    if !covered(row,col){col+=1;continue;}
                    let first=col;while col<mask.columns&&covered(row,col){col+=1;}
                    let r=CreateRectRgn((offset_x+first as f64*mask.cell*sx).floor()as i32,(offset_y+row as f64*mask.cell*sy).floor()as i32,(offset_x+col as f64*mask.cell*sx).ceil()as i32,(offset_y+(row+1)as f64*mask.cell*sy).ceil()as i32);
                    if r.is_null()||CombineRgn(region,region,r,2)==0 {if !r.is_null(){DeleteObject(r);}DeleteObject(region);return Err(std::io::Error::last_os_error().into());}
                    DeleteObject(r);
                }
            }
        }
        if expanded {if let Some(panel)=layout.and_then(|l|l.panel){
            let r=CreateRectRgn(panel.x,panel.y,panel.x+panel.width,panel.y+panel.height);
            if r.is_null()||CombineRgn(region,region,r,2)==0 {if !r.is_null(){DeleteObject(r);}DeleteObject(region);return Err(std::io::Error::last_os_error().into());}DeleteObject(r);
        }}
        // Store the key before the call, allowing synchronous resize re-entry.
        *LAST_REGION.lock().unwrap()=Some(key);
        if SetWindowRgn(hwnd,region,1)==0 {*LAST_REGION.lock().unwrap()=None;DeleteObject(region);return Err(std::io::Error::last_os_error().into());}
        // Windows owns the region after successful SetWindowRgn.
    }
    Ok(())
}
#[cfg(not(target_os="windows"))]
fn apply_hit_region(_window:&WebviewWindow,_expanded:bool)->tauri::Result<()> {Ok(())}

fn work_area(window:&WebviewWindow,anchor:Anchor)->tauri::Result<Option<Bounds>> {
    Ok(window.monitor_from_point(anchor.x as f64-1.0,anchor.y as f64-1.0)?.or(window.primary_monitor()?).map(|m|{let a=m.work_area();Bounds{x:a.position.x,y:a.position.y,width:a.size.width,height:a.size.height}}))
}
fn recover_visible(window:&WebviewWindow)->tauri::Result<()> {
 let pos=window.outer_position()?;let size=window.outer_size()?;let anchor=Anchor{x:pos.x+size.width as i32,y:pos.y+size.height as i32};
 if let Some(bounds)=work_area(window,anchor)?{let fitted=preferences::fit_position(anchor,size.width as i32,size.height as i32,bounds);if fitted.x!=pos.x||fitted.y!=pos.y {window.set_position(PhysicalPosition::new(fitted.x,fitted.y))?;}}
 Ok(())
}
fn record_anchor(window:&WebviewWindow,store:&Arc<Mutex<PreferenceStore>>)->Result<(),String> {
    let pos=window.outer_position().map_err(|e|e.to_string())?;let size=window.outer_size().map_err(|e|e.to_string())?;
    let mut prefs=store.lock().map_err(|e|e.to_string())?;
    let pet=WINDOW_LAYOUT.lock().unwrap().map(|l|l.pet).unwrap_or(Rect{x:0,y:0,width:size.width as i32,height:size.height as i32});
    prefs.values.anchor=Some(Anchor{x:pos.x+pet.x+pet.width,y:pos.y+pet.y+pet.height});prefs.save()
}
#[derive(Serialize)]
#[serde(rename_all="camelCase")]
pub(crate) struct PreferenceView { animations_enabled:bool, size:u16, panel_height:u16, warning:Option<String> }
#[tauri::command]
pub(crate) fn get_preferences(state:State<'_,PetState>)->Result<PreferenceView,String> {
    let p=state.preferences.lock().map_err(|e|e.to_string())?;Ok(PreferenceView{animations_enabled:p.values.animations_enabled,size:p.values.size,panel_height:p.values.panel_height,warning:p.warning.clone()})
}
#[tauri::command]
pub(crate) fn set_motion(state:State<'_,PetState>,enabled:bool)->Result<(),String> {
    let mut p=state.preferences.lock().map_err(|e|e.to_string())?;p.values.animations_enabled=enabled;p.save()
}
#[tauri::command]
pub(crate) fn set_expanded(window:WebviewWindow,state:State<'_,PetState>,expanded:bool,panel_height:Option<f64>)->Result<Layout,String> {
    layout_window(window,state,expanded,panel_height,true)
}
fn layout_window(window:WebviewWindow,state:State<'_,PetState>,expanded:bool,panel_height:Option<f64>,capture_anchor:bool)->Result<Layout,String> {
    let previous=state.expanded.load(Ordering::Relaxed);
    if capture_anchor&&!previous {record_anchor(&window,&state.preferences)?;}
    let values=state.preferences.lock().map_err(|e|e.to_string())?.values.clone();
    let anchor=values.anchor.ok_or("Window anchor missing")?;
    let scale=window.scale_factor().map_err(|e|e.to_string())?;
    let bounds=work_area(&window,anchor).map_err(|e|e.to_string())?.ok_or("Monitor missing")?;
    let layout=layout::arrange(anchor,values.size,scale,bounds,if expanded{Some(panel_height.unwrap_or(340.0))}else{None});
    state.expanded.store(true,Ordering::Relaxed);
    let result=(||->tauri::Result<()> {
        *WINDOW_LAYOUT.lock().unwrap()=Some(layout);
        window.set_size(tauri::PhysicalSize::new(layout.window.width as u32,layout.window.height as u32))?;
        window.set_position(PhysicalPosition::new(layout.window.x,layout.window.y))?;
        apply_hit_region(&window,expanded)?;Ok(())
    })();
    state.expanded.store(if result.is_ok(){expanded}else{previous},Ordering::Relaxed);
    result.map_err(|e|e.to_string())?;
    if !expanded {record_anchor(&window,&state.preferences)?;}
    Ok(layout)
}
#[tauri::command]
pub(crate) fn set_panel_height(window:WebviewWindow,state:State<'_,PetState>,height:u16)->Result<Layout,String>{
 if !(300..=760).contains(&height){return Err("Высота должна быть от 300 до 760 px".into());}
 {let mut p=state.preferences.lock().map_err(|e|e.to_string())?;p.values.panel_height=height;p.save()?;}
 let open=state.expanded.load(Ordering::Relaxed);layout_window(window,state,open,Some(height as f64),true)
}
#[tauri::command]
pub(crate) fn set_size(window:WebviewWindow,state:State<'_,PetState>,size:u16,panel_height:Option<f64>)->Result<Layout,String> {
    if !(100..=260).contains(&size){return Err("Размер должен быть от 100 до 260 px".into());}
    let expanded=state.expanded.load(Ordering::Relaxed);
    if !expanded {let _=record_anchor(&window,&state.preferences);}
    {let mut p=state.preferences.lock().map_err(|e|e.to_string())?;p.values.size=size;p.save()?;}
    set_expanded(window,state,expanded,panel_height)
}
struct GestureGuard(Arc<AtomicBool>);
impl Drop for GestureGuard { fn drop(&mut self){self.0.store(false,Ordering::Relaxed);} }

#[tauri::command]
pub(crate) async fn drag_pet(window:WebviewWindow,state:State<'_,PetState>,start_x:f64,start_y:f64)->Result<bool,String> {
    if !start_x.is_finite() || !start_y.is_finite() { return Err("Invalid pointer position".into()); }
    let active=state.gesture.clone();let store=state.preferences.clone();
    if active.swap(true,Ordering::Relaxed) { return Ok(true); }
    tauri::async_runtime::spawn_blocking(move|| {
        let _guard=GestureGuard(active);
        let result=(||->tauri::Result<bool>{
            let origin=window.inner_position()?;let initial_scale=window.scale_factor()?;
            let press_x=origin.x as f64+start_x*initial_scale;
            let press_y=origin.y as f64+start_y*initial_scale;
            let began=Instant::now();let mut dragged=false;
            loop {
                let cursor=window.cursor_position()?;
                dragged|=(cursor.x-press_x).hypot(cursor.y-press_y)>5.0*initial_scale;
                if dragged {
                    let scale=window.scale_factor()?;
                    window.set_position(PhysicalPosition::new((cursor.x-start_x*scale).round()as i32,(cursor.y-start_y*scale).round()as i32))?;
                }
                if !left_button_down() || began.elapsed()>Duration::from_secs(20) { break; }
                thread::sleep(Duration::from_millis(8));
            }
            if dragged {
                let pos=window.outer_position()?;let size=window.outer_size()?;
                if let Some(monitor)=window.current_monitor()?.or(window.primary_monitor()?) {
                    let a=monitor.work_area();let x=pos.x.clamp(a.position.x,(a.position.x+a.size.width as i32-size.width as i32).max(a.position.x));
                    let y=pos.y.clamp(a.position.y,(a.position.y+a.size.height as i32-size.height as i32).max(a.position.y));
                    window.set_position(PhysicalPosition::new(x,y))?;
                }
            }
            if dragged {let _=record_anchor(&window,&store);}
            Ok(dragged||began.elapsed()>Duration::from_millis(700))
        })();
        result.map_err(|e|e.to_string())
    }).await.map_err(|e|e.to_string())?
}

#[tauri::command]
pub(crate) fn hide_pet(app:tauri::AppHandle)->Result<(),String>{crate::set_pet_visible_inner(&app,false).map(|_|())}
pub(crate) fn show(window:&WebviewWindow){
 if window.state::<PetState>().ready.load(Ordering::Relaxed){let _=recover_visible(window);let _=window.unminimize();let _=window.show();let _=window.emit("pet-visibility",true);}
}
#[tauri::command]
pub(crate) fn pet_ready(window:WebviewWindow,state:State<'_,PetState>)->Result<(),String> {
    let p=state.preferences.lock().map_err(|e|e.to_string())?.values.clone();
    if let Some(anchor)=p.anchor {
        let scale=window.scale_factor().map_err(|e|e.to_string())?;let (w,h)=preferences::physical_size(p.size,scale);
        window.set_size(tauri::PhysicalSize::new(w as u32,h as u32)).map_err(|e|e.to_string())?;
        if let Some(bounds)=work_area(&window,anchor).map_err(|e|e.to_string())? {let pos=preferences::fit_position(anchor,w,h,bounds);window.set_position(PhysicalPosition::new(pos.x,pos.y)).map_err(|e|e.to_string())?;}
        apply_hit_region(&window,false).map_err(|e|e.to_string())?;
    }
    // Optional local QA snapshot, only when explicitly requested by the launching test.
    if let Ok(path)=std::env::var("DEBUGYCH_LAYOUT_REPORT") {if let (Ok(pos),Ok(size),Ok(scale))=(window.outer_position(),window.outer_size(),window.scale_factor()){
        let report=serde_json::json!({"scaleFactor":scale,"physicalPosition":{"x":pos.x,"y":pos.y},"physicalSize":{"width":size.width,"height":size.height},"preferences":p});
        let _=std::fs::write(path,report.to_string());
    }}
    state.ready.store(true,Ordering::Relaxed);if crate::context(window.app_handle()).pet_visible {show(&window);}Ok(())
}

pub(crate) fn setup(app:&tauri::AppHandle)->Result<(),Box<dyn std::error::Error>> {

            let window=app.get_webview_window("pet").expect("main window");
            let store=Arc::new(Mutex::new(PreferenceStore::load(crate::config_dir(app)?.join("pet/preferences.json"))));
            let scale=window.scale_factor()?;let height=store.lock().unwrap().values.size;window.set_size(LogicalSize::new(height as f64*5.0/6.0,height as f64))?;let size=window.outer_size()?;
            let fallback=if let Some(m)=window.primary_monitor()? {let a=m.work_area();Anchor{x:a.position.x+a.size.width as i32-(36.0*scale)as i32,y:a.position.y+a.size.height as i32-(30.0*scale)as i32}}else{Anchor{x:300,y:400}};
            let anchor=store.lock().unwrap().values.anchor.unwrap_or(fallback);
            let pos=if let Some(b)=work_area(&window,anchor)? {preferences::fit_position(anchor,size.width as i32,size.height as i32,b)}else{Anchor{x:0,y:0}};
            window.set_position(PhysicalPosition::new(pos.x,pos.y))?;
            store.lock().unwrap().values.anchor=Some(Anchor{x:pos.x+size.width as i32,y:pos.y+size.height as i32});
            app.manage(PetState{expanded:Arc::new(AtomicBool::new(false)),gesture:Arc::new(AtomicBool::new(false)),preferences:store.clone(),ready:Arc::new(AtomicBool::new(false))});
            let expanded=app.state::<PetState>().expanded.clone();
            apply_hit_region(&window,false)?;
            let resized_window=window.clone();let gesture=app.state::<PetState>().gesture.clone();
            window.on_window_event(move|event|{
                if matches!(event,WindowEvent::ScaleFactorChanged{..})&&!gesture.load(Ordering::Relaxed){
                    let state=resized_window.state::<PetState>();let open=expanded.load(Ordering::Relaxed);
                    let panel_height=WINDOW_LAYOUT.lock().unwrap().and_then(|l|l.panel.map(|p|p.height as f64/l.scale));
                    if let Ok(layout)=layout_window(resized_window.clone(),state,open,panel_height,false){let _=resized_window.emit("pet-layout",layout);}
                }
                if matches!(event,WindowEvent::Focused(true)){let _=resized_window.emit("pet-visibility",true);}
                if let WindowEvent::CloseRequested{api,..}=event{api.prevent_close();resized_window.state::<backend::Backend>().cancel_all();let _=crate::set_pet_visible_inner(resized_window.app_handle(),false);if let Ok(mut p)=store.lock(){let _=p.save();}}
            });

 Ok(())
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test] fn silhouette_has_clickable_body_and_transparent_padding() {
        let mask:HitMask=serde_json::from_str(include_str!("hit-mask.json")).unwrap();
        assert!(mask.contains(112.0,120.0));assert!(!mask.contains(0.0,0.0));
        assert!(!mask.contains(223.0,269.0));assert!(!mask.contains(-1.0,100.0));
    }
}
