export class SpriteClock {
  constructor(manifest) { this.manifest=manifest; this.state='idle'; this.started=0; this.frozen=false; }
  react(state,now) { if(!this.manifest.states[state])throw Error('Unsupported prototype state: '+state);this.state=state;this.started=now; }
  sample(now) {
    const clip=this.manifest.states[this.state],age=Math.max(0,now-this.started),frame=Math.floor(age*this.manifest.fps/1000);
    if(!clip.loop&&frame>=clip.frames){this.react('idle',now);return {state:'idle',frame:0};}
    const still=clip.loop?0:Math.floor(clip.frames/2);
    return {state:this.state,frame:this.frozen?still:frame%clip.frames};
  }
  nextDelay(now) {
    if(!this.frozen)return 1000/this.manifest.fps;
    const clip=this.manifest.states[this.state];
    return clip.loop?Infinity:Math.max(1,clip.frames*1000/this.manifest.fps-Math.max(0,now-this.started));
  }
}
