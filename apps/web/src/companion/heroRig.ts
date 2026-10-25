import{AnimationClip,AnimationMixer,LoopRepeat,Vector3,Quaternion,Matrix4,Mesh,SkinnedMesh,MeshStandardMaterial,MeshPhysicalMaterial,FrontSide,Color,type Object3D,type Bone}from'three';
const clamp=(x:number,a:number,b:number)=>Math.max(a,Math.min(b,x));
const V=(x=0,y=0,z=0)=>new Vector3(x,y,z);
function setWorldQ(o:Object3D,q:Quaternion){o.quaternion.copy(o.parent!.getWorldQuaternion(new Quaternion()).invert().multiply(q));o.updateMatrixWorld(true)}
function turnWorld(o:Object3D,from:Vector3,to:Vector3){setWorldQ(o,new Quaternion().setFromUnitVectors(from.normalize(),to.normalize()).multiply(o.getWorldQuaternion(new Quaternion())))}
export function createHeroRig(root:Object3D,clips:AnimationClip[]){
 const bone=(name:string)=>root.getObjectByName('mixamorig'+name)as Bone;
 const head=bone('Head'),neck=bone('Neck'),spine=bone('Spine2'),upper=bone('RightArm'),fore=bone('RightForeArm'),hand=bone('RightHand');
 const mag=root.getObjectByName('MagnifierRoot')!,lens=root.getObjectByName('Lens')as Mesh;
 const mixer=new AnimationMixer(root);const hold=mixer.clipAction(clips.find(c=>c.name==='hold_magnifier')!);hold.play();mixer.update(0);root.updateMatrixWorld(true);
 const fingerRest: [Bone,Quaternion][]=[];root.traverse(o=>{if(o instanceof Object&&o.type==='Bone'&&/RightHand(Index|Middle|Ring|Pinky|Thumb)/.test(o.name))fingerRest.push([o as Bone,o.quaternion.clone()])});
 const eyeLocal=head.worldToLocal(V(-.08196515,1.102,.207));const faceLocal=V(0,0,1).applyQuaternion(head.getWorldQuaternion(new Quaternion()).invert());
 lens.geometry.computeBoundingBox();const lensLocal=lens.geometry.boundingBox!.getCenter(V()).applyMatrix4(lens.matrix);
 const magLocalQ=mag.quaternion.clone(),magOffset=mag.position.clone(),mats:MeshStandardMaterial[]=[],leds:MeshStandardMaterial[]=[],morphs:Mesh[]=[];
 root.traverse(o=>{if(!(o instanceof Mesh))return;o.castShadow=true;o.receiveShadow=true;if(o.morphTargetDictionary)morphs.push(o);if(o.name==='Lens'||o.name==='LED_Ring'){const material=o.name==='Lens'?new MeshPhysicalMaterial({color:'#d8edff',metalness:0,roughness:.09,clearcoat:1,clearcoatRoughness:.12,ior:1.45,specularIntensity:1.2,transparent:true,opacity:.085,depthWrite:false,side:FrontSide,emissive:'#102335',emissiveIntensity:.16}):(o.material as MeshStandardMaterial).clone();o.material=material;mats.push(material);if(o.name==='Lens'){o.renderOrder=2}else leds.push(material)}});
 const L1=upper.getWorldPosition(V()).distanceTo(fore.getWorldPosition(V())),L2=fore.getWorldPosition(V()).distanceTo(hand.getWorldPosition(V()));
 const idleClip=clips.find(c=>c.name==='idle')!;mixer.stopAllAction();const idle=mixer.clipAction(idleClip).setLoop(LoopRepeat,Infinity);idle.play();mixer.update(0);const basePose: [Bone,Quaternion][]=[];root.traverse(o=>{if(o.type==='Bone')basePose.push([o as Bone,o.quaternion.clone()])});
 const carryQ=new Quaternion();const mat=new Matrix4(),metrics={lensRayError:0,lensNormalErrorDegrees:0,wristError:0,reachClamped:false,headPitch:0,headYaw:0,eye:[0,0,0],lens:[0,0,0],wrist:[0,0,0],lensEyeDistance:0,gazeErrorDegrees:0};
 function pose(dt:number,t:number,target:Vector3,attention:number,lift:number,happy:number,defeatTime:number,expression:{raised?:number;static?:boolean}={}){
  basePose.forEach(([b,q])=>b.quaternion.copy(q));mixer.update(dt);basePose.forEach(([b,q])=>q.copy(b.quaternion));fingerRest.forEach(([b,q])=>b.quaternion.copy(q));root.updateMatrixWorld(true);
  spine.quaternion.multiply(new Quaternion().setFromAxisAngle(V(1,0,0),.045*attention*(1-happy)-.045*happy));root.updateMatrixWorld(true);
  let eye=head.localToWorld(eyeLocal.clone()),dir=target.clone().sub(eye).normalize();
  const yaw=clamp(Math.atan2(dir.x,dir.z),-.36,.36)*attention,pitch=clamp(Math.atan2(-dir.y,Math.hypot(dir.x,dir.z)),-.12,.56)*attention;
  metrics.headPitch=pitch;metrics.headYaw=yaw;
  const neckDelta=new Quaternion().setFromAxisAngle(V(0,1,0),yaw*.25).multiply(new Quaternion().setFromAxisAngle(V(1,0,0),pitch*.25));setWorldQ(neck,neckDelta.multiply(neck.getWorldQuaternion(new Quaternion())));
  const currentForward=faceLocal.clone().applyQuaternion(head.getWorldQuaternion(new Quaternion()));const desired=V(Math.sin(yaw)*Math.cos(pitch),-Math.sin(pitch),Math.cos(yaw)*Math.cos(pitch));turnWorld(head,currentForward,desired);
  for(let i=0;i<4;i++){eye=head.localToWorld(eyeLocal.clone());dir=target.clone().sub(eye).normalize();const y=clamp(Math.atan2(dir.x,dir.z),-.36,.36)*attention,p=clamp(Math.atan2(-dir.y,Math.hypot(dir.x,dir.z)),-.12,.56)*attention;turnWorld(head,faceLocal.clone().applyQuaternion(head.getWorldQuaternion(new Quaternion())),V(Math.sin(y)*Math.cos(p),-Math.sin(p),Math.cos(y)*Math.cos(p)))}
  // A restrained single nod only after verified defeat. Restore mixer pose each frame.
  const nod=!expression.static&&defeatTime>2.55&&defeatTime<3.4?.22*Math.sin((defeatTime-2.55)/.85*Math.PI)**2:0;
  head.quaternion.multiply(new Quaternion().setFromAxisAngle(V(1,0,0),nod));root.updateMatrixWorld(true);eye=head.localToWorld(eyeLocal.clone());dir=target.clone().sub(eye).normalize();
  const right=V(0,1,0).cross(dir).normalize(),up=dir.clone().cross(right).normalize();const inspectQ=new Quaternion().setFromRotationMatrix(mat.makeBasis(right,up,dir));
  const magQ=carryQ.clone().slerp(inspectQ,lift);
  const inspectCenter=eye.clone().lerp(target,.23),carryCenter=V(-.18,.76,.25);const lensCenter=carryCenter.lerp(inspectCenter,lift);lensCenter.z+=.07*Math.sin(Math.PI*lift);
  const magPosition=lensCenter.clone().sub(lensLocal.clone().applyQuaternion(magQ));const handQ=magQ.clone().multiply(magLocalQ.clone().invert());const wristTarget=magPosition.sub(magOffset.clone().applyQuaternion(handQ));
  const S=upper.getWorldPosition(V()),to=wristTarget.clone().sub(S),distance=to.length(),d=clamp(distance,Math.abs(L1-L2)+.002,L1+L2-.003);to.normalize();const a=(L1*L1-L2*L2+d*d)/(2*d),h=Math.sqrt(Math.max(0,L1*L1-a*a));
  const pole=V(-.52,.59,.12).sub(S);pole.addScaledVector(to,-pole.dot(to)).normalize();const E=S.clone().addScaledVector(to,a).addScaledVector(pole,h),W=S.clone().addScaledVector(to,d);
  turnWorld(upper,fore.getWorldPosition(V()).sub(S),E.clone().sub(S));turnWorld(fore,hand.getWorldPosition(V()).sub(E),W.clone().sub(E));setWorldQ(hand,handQ);root.updateMatrixWorld(true);
  const actualLens=mag.localToWorld(lensLocal.clone()),actualDir=V(0,0,1).applyQuaternion(mag.getWorldQuaternion(new Quaternion()));const eyeBug=target.clone().sub(eye),rayT=actualLens.clone().sub(eye).dot(eyeBug)/eyeBug.lengthSq();
  metrics.gazeErrorDegrees=Math.acos(clamp(faceLocal.clone().applyQuaternion(head.getWorldQuaternion(new Quaternion())).dot(dir),-1,1))*180/Math.PI;metrics.lensRayError=actualLens.distanceTo(eye.clone().addScaledVector(eyeBug,rayT));metrics.lensNormalErrorDegrees=Math.acos(clamp(Math.abs(actualDir.dot(dir)),-1,1))*180/Math.PI;metrics.wristError=hand.getWorldPosition(V()).distanceTo(wristTarget);metrics.reachClamped=distance>d+.00001;metrics.eye=eye.toArray();metrics.lens=actualLens.toArray();metrics.wrist=hand.getWorldPosition(V()).toArray();metrics.lensEyeDistance=eye.distanceTo(actualLens);
  const blink=t%4.3;const b=!expression.static&&blink>2.55&&blink<2.80?Math.sin((blink-2.55)/.25*Math.PI):0;
  for(const m of morphs){const w=m.morphTargetInfluences!,dict=m.morphTargetDictionary!;const set=(n:string,v:number)=>{if(dict[n]!==undefined)w[dict[n]]=v};set('gripCorrectiveRight',1);set('smile',happy*.82);set('browRelax',happy*.95);set('browRaise',(expression.raised??0)*.65);set('browFurrow',attention*.24*(1-happy)*(1-(expression.raised??0)));set('eyeSquint',(attention*.18*(1-happy)+happy*.4)*(1-b));set('blinkLeft',b);set('blinkRight',b);for(const side of ['Left','Right'])set('lidCorrective'+side,2*Math.max(0,Math.min(b,1-b)-.5*attention*.18*(1-b)))}
  const color=new Color(attention>.7?'#ff4454':'#368ddd').lerp(new Color('#42d89b'),expression.static?happy:clamp((defeatTime-2.85)/.35,0,1));for(const m of leds){m.emissive.lerp(color,expression.static||dt===0?1:1-Math.exp(-dt*7));m.emissiveIntensity=1.1}
 }
 return{pose,metrics,root,mixer,dispose(){mixer.stopAllAction();mixer.uncacheRoot(root);mats.forEach(m=>m.dispose());const skeletons=new Set<SkinnedMesh['skeleton']>();root.traverse(o=>{if(o instanceof SkinnedMesh)skeletons.add(o.skeleton)});skeletons.forEach(s=>s.dispose())}};
}
