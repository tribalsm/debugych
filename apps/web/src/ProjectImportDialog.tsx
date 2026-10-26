import {useEffect,useRef,useState,useCallback} from 'react';
import {Dialog} from './ui';
type Project={id:string;name:string;demo:boolean;created_at:string};
type Props={onClose:()=>void;onComplete:(p:Project)=>void;create:(name:string,signal:AbortSignal)=>Promise<Project>;upload:(id:string,file:File,signal:AbortSignal)=>Promise<unknown>};
/** Uses the existing project and upload APIs. A partial import can resume. */
export function ProjectImportDialog({onClose,onComplete,create,upload}:Props){
 const[name,setName]=useState(''),[files,setFiles]=useState<File[]>([]),[requirements,setRequirements]=useState(''),[pending,setPending]=useState(false),[error,setError]=useState(''),[saved,setSaved]=useState<Project|null>(null),[count,setCount]=useState(0);
 const progress=useRef<{project?:Project;queue:File[];index:number}>({queue:[],index:0}),abort=useRef<AbortController|null>(null),alive=useRef(true);
 useEffect(()=>{alive.current=true;return()=>{alive.current=false;abort.current?.abort()}},[]);
 const close=useCallback(()=>{abort.current?.abort();onClose()},[onClose]);
 async function submit(){
  if(pending)return;setError('');
  if(files.some(f=>f.size>10*1024*1024||f.size===0)){setError('Файлы должны быть непустыми и не больше 10 МБ.');return;}
  setPending(true);abort.current=new AbortController();const signal=abort.current.signal;
  try{
   const state=progress.current;
   if(!state.project){state.project=await create(name.trim(),signal);if(!alive.current||signal.aborted)return;setSaved(state.project);state.queue=[...files,...(requirements.trim()?[new File([requirements.trim()],'requirements-'+crypto.randomUUID().slice(0,8)+'.md',{type:'text/markdown'})]:[])];}
   while(state.index<state.queue.length){const file=state.queue[state.index];try{await upload(state.project.id,file,signal)}catch(e){throw new Error(file.name+': '+(e as Error).message)}if(!alive.current||signal.aborted)return;state.index++;setCount(state.index);}
   if(alive.current&&!signal.aborted)onComplete(state.project);
  }catch(e){if(alive.current)setError(signal.aborted?'Загрузка остановлена. Уже сохранённые данные остаются в проекте.':(e as Error).message);}
  finally{if(alive.current)setPending(false);}
 }
 return <Dialog title="Новый проект" onClose={close}><form className="project-import" onSubmit={e=>{e.preventDefault();void submit()}}>
  <label>Название проекта<input required maxLength={120} value={name} disabled={pending||!!saved} onChange={e=>setName(e.target.value)} placeholder="Например, Billing API"/></label>
  <label>Исходники и документы<input aria-label="Файлы нового проекта" type="file" multiple accept=".zip,.py,.js,.mjs,.cjs,.ts,.tsx,.jsx,.html,.css,.json,.java,.md,.pdf,.docx" disabled={pending||!!saved} onChange={e=>setFiles(Array.from(e.target.files??[]))}/></label>
  {files.length>0&&<ul>{files.map((f,i)=><li key={i}>{f.name} · {(f.size/1024).toFixed(1)} КБ</li>)}</ul>}
  <label>Требования или ожидаемое поведение<textarea aria-label="Требования нового проекта" rows={3} maxLength={100000} value={requirements} disabled={pending||!!saved} onChange={e=>setRequirements(e.target.value)} placeholder="Опишите, что программа должна делать. Текст сохранится как Markdown-документ."/></label>
  <p>Можно добавить файлы позже в Workspace. ZIP: до 100 файлов / 30 МБ после распаковки, загрузка до 10 МБ. Создание и загрузка не обращаются к LLM.</p>
  {pending&&<p role="status">Сохраняю проект и файлы: {count} из {progress.current.queue.length||files.length}. Это не AI-анализ.</p>}
  {error&&<div role="alert" className="alert error">{saved?'Проект создан; импорт завершён не полностью. ':''}{error}</div>}
  <div className="project-actions"><button className="primary" disabled={pending||!name.trim()}>{saved?'Повторить оставшуюся загрузку':'Создать проект'}</button>{saved&&<button type="button" className="secondary" disabled={pending} onClick={()=>onComplete(saved)}>Открыть сохранённый проект</button>}</div>
 </form></Dialog>;
}
