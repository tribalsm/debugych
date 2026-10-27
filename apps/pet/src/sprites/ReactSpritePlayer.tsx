import{useEffect,useRef,type CSSProperties}from'react';
import{SpritePlayer,type PlayerInfo}from'./SpritePlayer.js';
import{type SpriteManifest}from'./manifest.js';
export interface SpritePlayerProps {manifest:SpriteManifest;state?:string;enabled?:boolean;paused?:boolean;className?:string;style?:CSSProperties;onInfo?:(info:PlayerInfo)=>void}
/** React owns the lifecycle, Canvas owns frames. No per-frame React state update is required. */
export function ReactSpritePlayer({manifest,state,enabled=true,paused=false,className,style,onInfo}:SpritePlayerProps){
 const canvas=useRef<HTMLCanvasElement>(null),player=useRef<SpritePlayer|null>(null),info=useRef(onInfo);info.current=onInfo;
 useEffect(()=>{const p=new SpritePlayer(canvas.current!,manifest,{onInfo:v=>info.current?.(v)});player.current=p;void p.ready();const visibility=()=>p.setSuspended(document.hidden);document.addEventListener('visibilitychange',visibility);visibility();return()=>{document.removeEventListener('visibilitychange',visibility);p.dispose();player.current=null;};},[manifest]);
 useEffect(()=>{if(state)void player.current?.play(state);},[manifest,state,enabled]);useEffect(()=>{const query=matchMedia('(prefers-reduced-motion:reduce)');const update=()=>player.current?.setEnabled(enabled&&!query.matches);update();query.addEventListener('change',update);return()=>query.removeEventListener('change',update);},[manifest,enabled]);useEffect(()=>player.current?.pause(paused),[manifest,paused]);
 return <canvas ref={canvas} className={className} style={style} aria-label="Дебагыч"/>;
}
