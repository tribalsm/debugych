use super::preferences::{Anchor,Bounds,fit_position,physical_size};
use serde::Serialize;
#[derive(Clone,Copy,Debug,Serialize,PartialEq)]
#[serde(rename_all="camelCase")]
pub struct Rect {pub x:i32,pub y:i32,pub width:i32,pub height:i32}
#[derive(Clone,Copy,Debug,Serialize,PartialEq)]
#[serde(rename_all="camelCase")]
pub struct Layout {pub window:Rect,pub pet:Rect,pub panel:Option<Rect>,pub scale:f64}
// Physical rectangles: keep the pet anchored while placing a separate adjacent
// popover inside one transparent host. The gap is excluded from its Win32 region.
pub fn arrange(anchor:Anchor,size:u16,scale:f64,bounds:Bounds,panel_height:Option<f64>)->Layout {
 let (pw,ph)=physical_size(size,scale);let pos=fit_position(anchor,pw,ph,bounds);
 let pet=Rect{x:pos.x,y:pos.y,width:pw,height:ph};
 let Some(height)=panel_height else {return Layout{window:pet,pet:Rect{x:0,y:0,..pet},panel:None,scale};};
 let gap=(12.0*scale).round()as i32;let width=(360.0*scale).round()as i32;
 let mut width=width.min(bounds.width as i32);let height=(height.clamp(300.0,760.0)*scale).ceil()as i32;
 let mut height=height.min(bounds.height as i32);let right=bounds.x+bounds.width as i32;let bottom=bounds.y+bounds.height as i32;
 let mut x=if pet.x+pw+gap+width<=right {pet.x+pw+gap}else if pet.x-gap-width>=bounds.x{pet.x-gap-width}else{(pet.x+pw-width).clamp(bounds.x,(right-width).max(bounds.x))};
 let mut y=pet.y;if y+height>bottom{y=(pet.y+ph-height).max(bounds.y);}
 // Very narrow work areas cannot fit side by side. Prefer above/below.
 if x<pet.x+pw&&x+width>pet.x {
  let above=(pet.y-gap-bounds.y).max(0);let below=(bottom-pet.y-ph-gap).max(0);
  if above.max(below)>=(96.0*scale)as i32 {if above>=below{height=height.min(above);y=pet.y-gap-height;}else{height=height.min(below);y=pet.y+ph+gap;}}
  else {let left=(pet.x-gap-bounds.x).max(0);let right_space=(right-pet.x-pw-gap).max(0);if left.max(right_space)>0{width=width.min(left.max(right_space));x=if left>=right_space{pet.x-gap-width}else{pet.x+pw+gap};}}
 }
 let left=x.min(pet.x);let top=y.min(pet.y);let window=Rect{x:left,y:top,width:(x+width).max(pet.x+pw)-left,height:(y+height).max(pet.y+ph)-top};
 Layout{window,pet:Rect{x:pet.x-left,y:pet.y-top,..pet},panel:Some(Rect{x:x-left,y:y-top,width,height}),scale}
}
#[cfg(test)]mod tests {
 use super::*;
 #[test]fn resized_panels_keep_the_same_pet_anchor_across_dpi(){for scale in [1.0,1.25,1.5,2.0]{for height in [300.0,520.0,650.0,760.0]{let b=Bounds{x:-1920,y:-300,width:1920,height:1080};let anchor=Anchor{x:-30,y:760};let a=arrange(anchor,160,scale,b,Some(height));let p=a.panel.unwrap();let c=arrange(anchor,160,scale,b,None);assert_eq!(a.window.x+a.pet.x,c.window.x);assert_eq!(a.window.y+a.pet.y,c.window.y);assert!(a.window.y>=b.y);assert!(a.window.y+a.window.height<=b.y+b.height as i32);assert!(p.x+p.width<=a.pet.x||a.pet.x+a.pet.width<=p.x||p.y+p.height<=a.pet.y||a.pet.y+a.pet.height<=p.y);}}}
 #[test]fn narrow_and_short_work_areas_keep_pet_separate(){for bounds in [Bounds{x:0,y:0,width:320,height:480},Bounds{x:-800,y:0,width:800,height:480},Bounds{x:0,y:0,width:1024,height:600}]{for anchor in [Anchor{x:bounds.x+300,y:bounds.y+400},Anchor{x:bounds.x+100,y:bounds.y+200}]{let l=arrange(anchor,160,1.0,bounds,Some(680.0));let p=l.panel.unwrap();let pet=l.pet;assert!(p.x+p.width<=pet.x||pet.x+pet.width<=p.x||p.y+p.height<=pet.y||pet.y+pet.height<=p.y);assert!(l.window.x>=bounds.x&&l.window.y>=bounds.y);assert!(l.window.x+l.window.width<=bounds.x+bounds.width as i32&&l.window.y+l.window.height<=bounds.y+bounds.height as i32);}}}
 #[test]fn panels_fit_edges_and_do_not_cover_pet_at_all_dpi(){
  for scale in [1.0,1.25,1.5,2.0]{for size in [100,160,260]{for bounds in [Bounds{x:0,y:0,width:1920,height:1080},Bounds{x:-2560,y:-1440,width:2560,height:1440}]{
   for anchor in [Anchor{x:bounds.x+250,y:bounds.y+300},Anchor{x:bounds.x+bounds.width as i32,y:bounds.y+bounds.height as i32},Anchor{x:bounds.x+100,y:bounds.y+100}]{
    let l=arrange(anchor,size,scale,bounds,Some(360.0));let p=l.panel.unwrap();let pet=l.pet;
    assert!(l.window.x>=bounds.x&&l.window.y>=bounds.y);assert!(l.window.x+l.window.width<=bounds.x+bounds.width as i32);assert!(l.window.y+l.window.height<=bounds.y+bounds.height as i32);
    assert!(p.x+p.width<=pet.x||pet.x+pet.width<=p.x||p.y+p.height<=pet.y||pet.y+pet.height<=p.y);
    let closed=arrange(anchor,size,scale,bounds,None);assert_eq!(l.window.x+pet.x,closed.window.x);assert_eq!(l.window.y+pet.y,closed.window.y);
   }
  }}}
 }
}
