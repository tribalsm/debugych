import{test}from'node:test';import assert from'node:assert/strict';import fs from'node:fs';
import{AnimationStateController}from'../web/player/sprites/AnimationStateController.js';
import{InteractivePetController}from'../web/player/sprites/InteractivePetController.js';
import{IdleBehaviorController}from'../web/player/sprites/IdleBehaviorController.js';
import{isShortClick}from'../web/player/sprites/gesture.js';
import{validateManifest}from'../web/player/sprites/manifest.js';
const manifest=JSON.parse(fs.readFileSync(new URL('../web/assets/manifest.json',import.meta.url),'utf8'));
function harness(){let now=0,id=0,can=true;const jobs=new Map(),calls=[];const options={now:()=>now,random:()=>.5,schedule:(f,ms)=>{jobs.set(++id,{f,ms});return id;},cancel:id=>jobs.delete(id),canReact:()=>can,react:kind=>{calls.push(kind);return true;},cancelReaction:()=>{},togglePanel:()=>calls.push('panel')};const c=new InteractivePetController(options);return{c,calls,jobs,options,time:t=>now=t,can:v=>can=v,run(ms){const row=[...jobs].find(([,v])=>v.ms===ms);assert.ok(row);jobs.delete(row[0]);row[1].f();}};}
test('local reaction uses existing idle frames, finishes and preserves task state',()=>{
 const c=new AnimationStateController(validateManifest(manifest));c.sample(0);assert.equal(c.react('click',100),true);assert.equal(c.sample(180).reaction,'click');assert.equal(c.requested,'idle');assert.equal(c.sample(1000).reaction,undefined);
 c.play('analyzing',1100,true);assert.equal(c.react('hover',1200),false);assert.equal(c.sample(1500).state,'analyzing');
});
test('system animation cancels local reaction, leave resumes idle, disabled and paused reject reactions',()=>{
 const c=new AnimationStateController(manifest);c.react('hover',0);c.play('success',50);assert.equal(c.sample(60).reaction,undefined);c.play('idle',100);c.react('click',100);c.cancelReaction(200);assert.equal(c.sample(250).requested,'idle');assert.equal(c.sample(250).reaction,undefined);
 c.setPaused(true,300);assert.equal(c.react('click',310),false);c.setPaused(false,400);c.setEnabled(false,410);assert.equal(c.react('hover',500),false);assert.equal(c.nextDelay(1000),Infinity);
});
test('hover is delayed once, rate limited, and canceled on leave without queues',()=>{
 const h=harness();h.c.enter();for(let i=0;i<50;i++)h.c.enter();assert.equal(h.jobs.size,1);h.run(350);assert.deepEqual(h.calls,['hover']);h.c.leave();h.time(1000);h.c.enter();assert.equal(h.jobs.size,0);h.c.leave();h.time(7000);h.c.enter();h.c.leave();assert.ok([...h.jobs.values()].every(j=>j.ms!==350));h.c.dispose();assert.equal(h.jobs.size,0);
});
test('click opens immediately, only neutral local reaction; drag and hold never open',()=>{
 const h=harness();h.c.beginDrag();h.c.endGesture(true);assert.deepEqual(h.calls,[]);h.c.beginDrag();h.c.endGesture(false);assert.deepEqual(h.calls,['click','panel']);h.time(100);h.c.click();assert.deepEqual(h.calls,['click','panel','panel']);assert.ok(h.calls.every(x=>!['bug_found','success','analyzing'].includes(x)));h.c.dispose();
 assert.ok(isShortClick(3,2,120));assert.ok(!isShortClick(6,0,100));assert.ok(!isShortClick(0,0,900));
});
test('busy system hover leaves system untouched and local disabled click still opens panel',()=>{
 const h=harness();h.can(false);h.c.enter();assert.equal(h.jobs.size,0);h.c.click();assert.deepEqual(h.calls,['panel']);h.c.setEnabled(false);h.can(true);h.c.click();assert.deepEqual(h.calls,['panel','panel']);h.c.dispose();
});
test('idle variations have one irregular timer, stop hidden, paused or disabled, dispose cleanly',()=>{
 const h=harness();assert.equal(h.jobs.size,1);h.run(19500);assert.deepEqual(h.calls,['idle_variation']);assert.equal(h.jobs.size,1);h.c.setVisible(false);assert.equal(h.jobs.size,0);h.c.setVisible(true);assert.equal(h.jobs.size,1);h.c.setEnabled(false);assert.equal(h.jobs.size,0);h.c.setEnabled(true);h.can(false);h.c.refresh();assert.equal(h.jobs.size,0);h.c.dispose();assert.equal(h.jobs.size,0);
});
test('hundreds of panel toggles and pointer entries never accumulate timers',()=>{
 const h=harness();for(let i=0;i<300;i++){h.c.enter();h.c.leave();h.c.setPanel(true);h.c.setPanel(false);assert.ok(h.jobs.size<=1);}h.c.dispose();assert.equal(h.jobs.size,0);
});
test('idle timer intervals vary within quiet limits and disposal prevents restart',()=>{
 const jobs=new Map();let id=0,r=0;const c=new IdleBehaviorController(()=>{}, {random:()=>r,schedule:(f,ms)=>{jobs.set(++id,{f,ms});return id;},cancel:id=>jobs.delete(id)});c.setActive(true);assert.equal([...jobs.values()][0].ms,12000);const j=[...jobs.values()][0];jobs.clear();r=1;j.f();assert.equal([...jobs.values()][0].ms,27000);c.dispose();c.setActive(true);assert.equal(jobs.size,0);
});
test('reaction metadata rejects out of range or nonexistent source frames',()=>{
 const m=structuredClone(manifest);m.reactions.click.frames[0].index=999;assert.throws(()=>validateManifest(m));const b=structuredClone(manifest);b.reactions.hover.source='invented';assert.throws(()=>validateManifest(b));
});

test('six simulated hours of irregular idle remain one timer with no reaction queue',()=>{
 const h=harness();for(let t=0;t<6*3600*1000;t+=19500){h.time(t);h.run(19500);assert.equal(h.jobs.size,1);}assert.ok(h.calls.length>1000);h.c.dispose();assert.equal(h.jobs.size,0);
});
