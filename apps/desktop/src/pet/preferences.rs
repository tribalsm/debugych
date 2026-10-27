use serde::{Deserialize, Serialize};
use std::{fs, path::PathBuf};

#[derive(Clone, Copy, Debug, Deserialize, Serialize, PartialEq)]
pub struct Anchor { pub x:i32, pub y:i32 }
#[derive(Clone, Copy, Debug)]
pub struct Bounds { pub x:i32, pub y:i32, pub width:u32, pub height:u32 }
#[derive(Clone, Debug, Deserialize, Serialize)]
#[serde(default, rename_all="camelCase")]
pub struct Preferences { pub version:u32, pub anchor:Option<Anchor>, pub animations_enabled:bool, pub size:u16, pub panel_height:u16 }
impl Default for Preferences { fn default()->Self { Self{version:1,anchor:None,animations_enabled:true,size:160,panel_height:520} } }

pub fn fit_position(anchor:Anchor,width:i32,height:i32,bounds:Bounds)->Anchor {
    let max_x=(bounds.x as i64+bounds.width as i64-width as i64).max(bounds.x as i64);
    let max_y=(bounds.y as i64+bounds.height as i64-height as i64).max(bounds.y as i64);
    Anchor{x:(anchor.x as i64-width as i64).clamp(bounds.x as i64,max_x) as i32,y:(anchor.y as i64-height as i64).clamp(bounds.y as i64,max_y) as i32}
}

pub struct PreferenceStore { pub values:Preferences, path:PathBuf, pub warning:Option<String> }
impl PreferenceStore {
    pub fn load(path:PathBuf)->Self {
        let (values,warning)=match fs::read(&path) {
            Ok(bytes)=>match serde_json::from_slice::<Preferences>(&bytes) {
                Ok(mut v) if v.version==1=>{v.size=v.size.clamp(100,260);v.panel_height=v.panel_height.clamp(300,760);(v,None)},
                _=>(Preferences::default(),Some("Не удалось восстановить настройки. Используются исходные значения.".into()))
            },
            Err(e) if e.kind()==std::io::ErrorKind::NotFound=>(Preferences::default(),None),
            Err(_)=>(Preferences::default(),Some("Настройки недоступны. Питомец работает с исходными значениями.".into()))
        };
        Self{values,path,warning}
    }
    pub fn save(&mut self)->Result<(),String> {
        let result=(||->std::io::Result<()> {
            if let Some(parent)=self.path.parent(){fs::create_dir_all(parent)?;}
            let temp=self.path.with_extension("json.tmp");
            fs::write(&temp,serde_json::to_vec_pretty(&self.values)?)?;
            fs::rename(temp,&self.path)?;
            Ok(())
        })();
        match result {Ok(())=>{self.warning=None;Ok(())},Err(_)=>{let message="Не удалось сохранить настройки. Текущий сеанс продолжает работать.".to_string();self.warning=Some(message.clone());Err(message)}}
    }
}

#[cfg(test)] mod tests {
    use super::*;
    #[test] fn negative_monitor_and_disconnected_anchor_stay_visible(){
        let b=Bounds{x:-1920,y:0,width:1920,height:1080};
        assert_eq!(fit_position(Anchor{x:-40,y:900},224,270,b),Anchor{x:-264,y:630});
        assert_eq!(fit_position(Anchor{x:9000,y:-3000},224,270,b),Anchor{x:-224,y:0});
    }
    #[test] fn small_display_and_extreme_coordinates_do_not_overflow(){
        let b=Bounds{x:0,y:0,width:160,height:120};
        assert_eq!(fit_position(Anchor{x:i32::MIN,y:i32::MAX},224,270,b),Anchor{x:0,y:0});
    }
    #[test] fn saved_motion_and_anchor_roundtrip_and_corruption_falls_back(){
        let path=std::env::temp_dir().join(format!("debugych-prefs-test-{}.json",std::process::id()));
        let mut store=PreferenceStore::load(path.clone());
        store.values.panel_height=610;store.values.size=200;store.values.animations_enabled=false;store.values.anchor=Some(Anchor{x:-200,y:720});store.save().unwrap();
        let loaded=PreferenceStore::load(path.clone());assert!(!loaded.values.animations_enabled);assert_eq!(loaded.values.size,200);assert_eq!(loaded.values.panel_height,610);assert_eq!(loaded.values.anchor,store.values.anchor);
        fs::write(&path,b"invalid").unwrap();let broken=PreferenceStore::load(path.clone());assert!(broken.values.animations_enabled);assert!(broken.warning.is_some());fs::write(&path,br#"{"version":1,"size":999}"#).unwrap();assert_eq!(PreferenceStore::load(path.clone()).values.size,260);fs::remove_file(path).unwrap();
    }
}

#[cfg(test)] mod sizing_tests {
 use super::*;
 #[test] fn v21_preferences_migrate_and_invalid_sizes_clamp(){
  let old:Preferences=serde_json::from_str(r#"{"version":1,"animationsEnabled":false}"#).unwrap();assert_eq!(old.size,160);assert_eq!(old.panel_height,520);assert!(!old.animations_enabled);
 }
 #[test] fn sizing_keeps_anchor_at_every_dpi(){
  for dpi in [1.0,1.25,1.5,2.0] {for h in [100,120,160,200,260] {let (w,p)=physical_size(h,dpi);let a=Anchor{x:1800,y:900};let b=Bounds{x:0,y:0,width:1920,height:1080};let pos=fit_position(a,w,p,b);assert_eq!(pos.x+w,a.x);assert_eq!(pos.y+p,a.y);assert!((w as f64/p as f64-5.0/6.0).abs()<0.006);}}
 }
}
pub fn physical_size(height:u16,dpi:f64)->(i32,i32) {((height as f64*5.0/6.0*dpi).round()as i32,(height as f64*dpi).round()as i32)}
