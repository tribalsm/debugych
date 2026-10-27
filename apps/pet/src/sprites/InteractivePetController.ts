import{type LocalReaction}from'./manifest.js';
import{IdleBehaviorController,type BehaviorClock}from'./IdleBehaviorController.js';
export interface InteractiveOptions extends BehaviorClock {now?:()=>number;react:(kind:LocalReaction)=>boolean;cancelReaction:()=>void;canReact:()=>boolean;togglePanel:()=>void}
/** Local input only. It never invents or changes a task/system state. */
export class InteractivePetController {
 private hoverTimer:unknown=null;private hovered=false;private dragging=false;private panel=false;private enabled=true;private visible=true;private disposed=false;private lastHover=-Infinity;private lastClick=-Infinity;
 readonly idle:IdleBehaviorController;private now:()=>number;
 constructor(private options:InteractiveOptions){this.now=options.now??(()=>performance.now());this.idle=new IdleBehaviorController(()=>{if(this.available())options.react('idle_variation');},options);this.refresh();}
 private available(){return !this.disposed&&this.enabled&&this.visible&&!this.dragging&&!this.panel&&this.options.canReact();}
 private clearHover(){if(this.hoverTimer!==null)this.options.cancel(this.hoverTimer);this.hoverTimer=null;}
 refresh(){this.idle.setActive(this.available()&&!this.hovered);}
 enter(){if(this.hovered||this.disposed)return;this.hovered=true;this.refresh();if(!this.available()||this.now()-this.lastHover<6500)return;
  this.hoverTimer=this.options.schedule(()=>{this.hoverTimer=null;if(this.hovered&&this.available()){this.lastHover=this.now();this.options.react('hover');}},350);
 }
 leave(){if(!this.hovered)return;this.hovered=false;this.clearHover();this.options.cancelReaction();this.refresh();}
 beginDrag(){this.dragging=true;this.clearHover();this.options.cancelReaction();this.refresh();}
 endGesture(dragged:boolean){this.dragging=false;if(!dragged)this.click();this.refresh();}
 click(){if(this.disposed)return;this.clearHover();if(this.enabled&&this.visible&&this.options.canReact()&&this.now()-this.lastClick>=800){this.lastClick=this.now();this.options.react('click');}this.options.togglePanel();}
 setPanel(value:boolean){this.panel=value;this.clearHover();this.refresh();}
 setEnabled(value:boolean){this.enabled=value;if(!value){this.clearHover();this.options.cancelReaction();}this.refresh();}
 setVisible(value:boolean){this.visible=value;if(!value){this.hovered=false;this.clearHover();this.options.cancelReaction();}this.refresh();}
 systemChanged(){this.clearHover();this.options.cancelReaction();this.refresh();}
 dispose(){this.disposed=true;this.clearHover();this.idle.dispose();}
}
