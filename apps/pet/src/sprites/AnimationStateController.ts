import{resolveClip,type SpriteManifest,type LocalReaction}from'./manifest.js';
export interface Sample {requested:string;state:string;frame:number;finished:boolean;reaction?:LocalReaction}
export class AnimationStateController {
 requested:string;private elapsed=0;private last:number|null=null;private paused=false;private suspended=false;private enabled=true;private repeat=false;private local:{kind:LocalReaction;elapsed:number}|null=null;
 constructor(readonly manifest:SpriteManifest){this.requested=manifest.defaultState;}
 private tick(now:number){if(this.last!==null&&this.enabled&&!this.paused&&!this.suspended){const dt=Math.max(0,now-this.last);if(this.local)this.local.elapsed+=dt;else this.elapsed+=dt;}this.last=now;}
 play(state:string,now:number,repeat=false){resolveClip(this.manifest,state);this.local=null;this.requested=state;this.elapsed=0;this.last=now;this.paused=false;this.repeat=repeat;}
 setPaused(value:boolean,now:number){this.tick(now);this.paused=value;}
 setSuspended(value:boolean,now:number){this.tick(now);this.suspended=value;}
 setEnabled(value:boolean,now:number){this.tick(now);this.enabled=value;if(!value){this.local=null;this.requested=this.manifest.defaultState;this.elapsed=0;this.repeat=false;}}
 react(kind:LocalReaction,now:number){
  this.tick(now);if(!this.enabled||this.paused||this.suspended||this.requested!==this.manifest.defaultState||!this.manifest.reactions?.[kind])return false;
  if(this.local&&kind!=='click')return false;this.local={kind,elapsed:0};return true;
 }
 cancelReaction(now:number){this.tick(now);this.local=null;}
 get isReacting(){return this.local!==null;}
 get isSuspended(){return this.suspended;}get isEnabled(){return this.enabled;}get isPaused(){return this.paused;}
 sample(now:number):Sample {
  this.tick(now);let r=resolveClip(this.manifest,this.requested);let finished=false;
  if(!this.enabled)return{requested:this.requested,state:this.manifest.defaultState,frame:this.manifest.states[this.manifest.defaultState].neutralFrame??0,finished:false};
  if(!r.static&&!r.clip.loop&&!this.repeat&&this.elapsed>=r.clip.durationMs){this.requested=r.clip.next??this.manifest.defaultState;this.elapsed=0;r=resolveClip(this.manifest,this.requested);finished=true;}
  if(this.local){const reaction=this.manifest.reactions![this.local.kind]!;let age=this.local.elapsed;
   for(const f of reaction.frames){if(age<f.durationMs)return{requested:this.requested,state:reaction.source,frame:f.index,finished:false,reaction:this.local.kind};age-=f.durationMs;}
   this.local=null;
  }
  if(r.static)return{requested:this.requested,state:r.state,frame:r.clip.neutralFrame??0,finished};
  let age=this.elapsed%r.clip.durationMs;let frame=0;for(const f of r.clip.frameData!){if(age<f.durationMs)break;age-=f.durationMs;frame++;}
  return{requested:this.requested,state:r.state,frame:Math.min(frame,r.clip.frames-1),finished};
 }
 nextDelay(now:number):number {
  const s=this.sample(now),r=resolveClip(this.manifest,this.requested);if(!this.enabled||this.paused||this.suspended||r.static)return Infinity;
  if(this.local){let age=this.local.elapsed;for(const f of this.manifest.reactions![this.local.kind]!.frames){if(age<f.durationMs)return Math.max(1,f.durationMs-age);age-=f.durationMs;}}
  const age=this.elapsed%r.clip.durationMs,start=r.clip.frameData!.slice(0,s.frame).reduce((sum,f)=>sum+f.durationMs,0);
  return Math.max(1,start+r.clip.frameData![s.frame].durationMs-age);
 }
}
