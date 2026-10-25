import{Mesh}from'three';import type{Object3D}from'three';import type{AgentState}from'../MascotSlot';
const smooth=(t:number)=>{t=Math.max(0,Math.min(1,t));return t*t*(3-2*t)};
/** Time-continuous eyelid motion, independent of the skeletal mixer. */
export class DebugychFacialController{
 private meshes:Mesh[]=[];private time=0;private next=3.6;private blinkStart=-10;private values:Record<string,number>={};
 constructor(root:Object3D){root.traverse(o=>{if(o instanceof Mesh&&o.morphTargetDictionary)this.meshes.push(o)})}
 update(dt:number,state:AgentState,stateTime:number,grip:boolean){this.time+=dt;if(this.time>=this.next){this.blinkStart=this.time;this.next=this.time+3.7+Math.sin(this.time*1.7)**2*1.5}const age=this.time-this.blinkStart;const blink=age<0||age>.28?0:age<.09?smooth(age/.09):age<.15?1:1-smooth((age-.15)/.13);const happy=state==='success'?Math.max(.25,1-stateTime/4):0;const surprise=state==='bug_found'?Math.max(.15,1-stateTime/2.6):0;
 const targets:Record<string,number>={browFurrow:state==='error'?.35:state==='fixing'?.24:state==='analyzing'||state==='generating'?.20:state==='testing'?.13:.055,browRaise:surprise*.65,surprise:surprise*.65,browAsymmetry:state==='error'?.2:state==='fixing'?.09:0,browRelax:happy*.7,smile:happy*.6,eyeSquint:happy*.18+(['fixing','analyzing','generating','testing'].includes(state)?.16:0),gripCorrectiveRight:grip?1:0};
 for(const[k,v]of Object.entries(targets))this.values[k]=(this.values[k]??0)+(v-(this.values[k]??0))*(1-Math.exp(-dt*12));
 for(const m of this.meshes){const d=m.morphTargetDictionary!,w=m.morphTargetInfluences!;for(const[k,v]of Object.entries(this.values))if(d[k]!==undefined)w[d[k]]=k==='eyeSquint'?v*(1-blink):v;for(const side of['Left','Right']){if(d['blink'+side]!==undefined)w[d['blink'+side]]=blink;if(d['lidCorrective'+side]!==undefined)w[d['lidCorrective'+side]]=2*Math.max(0,Math.min(blink,1-blink)-.5*(this.values.eyeSquint??0)*(1-blink))}}
 }
}
