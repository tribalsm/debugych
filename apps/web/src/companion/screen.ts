export type LaptopScreenState =
 |{kind:'idle'}
 |{kind:'analyzing';project:string;detail:string}
 |{kind:'fixing';patchId:string;diff:string}
 |{kind:'testing';runId:string;command:string;lines:string[]}
 |{kind:'success';verificationId:string;passed:true;summary:string}
 |{kind:'error';message:string;runId?:string};
export type ScreenContent={title:string;subtitle:string;lines:string[];accent:string;idle:boolean};
const clean=(s:string)=>s.replace(/[\x00-\x08\x0b-\x1f\x7f]/g,'').replace(/\t/g,'  ');
export function screenContent(state:LaptopScreenState):ScreenContent{
 const base={idle:false,accent:'#67ccff'};
 switch(state.kind){
  case'idle':return{...base,title:'ГОТОВ К РАБОТЕ',subtitle:'Ожидание данных приложения',lines:[],idle:true};
  case'analyzing':return{...base,title:'АНАЛИЗ ПРОЕКТА',subtitle:clean(state.project),lines:[clean(state.detail)]};
  case'fixing':return{...base,title:'ПРЕДЛОЖЕННЫЙ DIFF',subtitle:clean(state.patchId)+' · ещё не проверен',lines:clean(state.diff).split('\n')};
  case'testing':return{...base,title:'ПРОВЕРКА',subtitle:clean(state.runId),lines:['$ '+clean(state.command),...state.lines.map(clean)]};
  case'success':return state.passed===true&&state.verificationId.trim()?{...base,title:'ИСПРАВЛЕНИЕ ПРОВЕРЕНО',subtitle:clean(state.verificationId),lines:[clean(state.summary)],accent:'#66dfaf'}:{...base,title:'НЕТ ПОДТВЕРЖДЕНИЯ',subtitle:'Нужен результат реальной проверки',lines:[],accent:'#ff9a8e'};
  case'error':return{...base,title:'ПРОВЕРКА НЕУСПЕШНА',subtitle:clean(state.runId??'Ошибка проверки'),lines:[clean(state.message)],accent:'#ff9a8e'};
 }
}
export function wrapLines(lines:string[],width=64,max=13){const result:string[]=[];for(const line of lines){if(!line.length)result.push('');else for(let i=0;i<line.length;i+=width)result.push(line.slice(i,i+width));}if(result.length>max)return[...result.slice(0,max-1),'… продолжение в журнале приложения'];return result;}
export function paintScreen(canvas:HTMLCanvasElement,state:LaptopScreenState,demo=false){
 const ctx=canvas.getContext('2d');if(!ctx)throw Error('Canvas 2D unavailable');const data=screenContent(state);ctx.clearRect(0,0,1680,920);ctx.fillStyle='#081521';ctx.fillRect(0,0,1680,920);ctx.fillStyle='#132b3c';ctx.fillRect(0,0,1680,94);ctx.font='bold 36px Consolas, monospace';ctx.fillStyle='#9bcde5';ctx.fillText('ДЕБАГЫЧ / FIX & VERIFY',48,60);if(demo){ctx.fillStyle='#ffc985';ctx.font='26px Consolas, monospace';ctx.fillText('РУЧНОЙ ПРИМЕР',1325,59)}
 ctx.fillStyle=data.accent;ctx.font='bold 52px Consolas, monospace';ctx.fillText(data.title,48,172);ctx.fillStyle='#88a9ba';ctx.font='30px Consolas, monospace';ctx.fillText(data.subtitle.slice(0,82),48,225);
 if(data.idle){ctx.font='bold 178px Consolas, monospace';ctx.fillStyle=data.accent;ctx.fillText('</>',660,520);ctx.font='36px Consolas, monospace';ctx.fillStyle='#88a9ba';ctx.fillText('Состояние задаёт приложение',510,650);return}
 ctx.font='34px Consolas, monospace';wrapLines(data.lines).forEach((line,i)=>{ctx.fillStyle=line.startsWith('+')?'#80e7b8':line.startsWith('-')?'#ff9b95':line.startsWith('@@')?'#6fcbff':'#d5e5ef';ctx.fillText(line,48,305+i*44)})
}
