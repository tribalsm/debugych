export interface BehaviorClock {schedule:(f:()=>void,ms:number)=>unknown;cancel:(id:unknown)=>void;random?:()=>number}
/** One cancellable, irregular wake-up. Rendering remains owned by SpritePlayer. */
export class IdleBehaviorController {
 private timer:unknown=null;private active=false;private disposed=false;
 constructor(private act:()=>void,private clock:BehaviorClock){}
 setActive(value:boolean){if(this.disposed||value===this.active)return;this.active=value;this.clear();if(value)this.plan();}
 private clear(){if(this.timer!==null)this.clock.cancel(this.timer);this.timer=null;}
 private plan(){this.timer=this.clock.schedule(()=>{this.timer=null;if(!this.active||this.disposed)return;this.act();this.plan();},12000+(this.clock.random??Math.random)()*15000);}
 get pending(){return this.timer!==null;}
 dispose(){this.disposed=true;this.active=false;this.clear();}
}
