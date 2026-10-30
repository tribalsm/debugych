import {useEffect,useRef,useState} from 'react';
import {Search} from 'lucide-react';
import {CodeView} from './ui';
type Result={mode:string;encoder:string;chunks:number;matches:{path:string;start_line:number;end_line:number;content:string;score:number}[]};
export function ContextSearch({projectId,disabled}:{projectId:string;disabled:boolean}){
 const [query,setQuery]=useState(''),[busy,setBusy]=useState(false),[error,setError]=useState(''),[result,setResult]=useState<Result>();
 const request=useRef<AbortController|null>(null);
 useEffect(()=>()=>request.current?.abort(),[]);
 async function search(){
  request.current?.abort();const controller=new AbortController();request.current=controller;setBusy(true);setError('');setResult(undefined);
  try{
   const response=await fetch(`/api/projects/${encodeURIComponent(projectId)}/context-search`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({query:query.trim(),limit:6}),signal:controller.signal});
   if(!response.ok)throw new Error(response.status===429?'Сервис занят. Повторите позже.':'Не удалось выполнить поиск. Проверьте соединение, доступ и объём проекта.');
   const value=await response.json() as Result;if(!Array.isArray(value.matches))throw new Error('Сервер вернул некорректный ответ.');setResult(value);
  }catch(e){if(!controller.signal.aborted)setError(e instanceof Error?e.message:'Поиск недоступен')}
  finally{if(!controller.signal.aborted)setBusy(false)}
 }
 return <details className="panel technical-disclosure context-search"><summary>Поиск по коду и требованиям</summary><p>Локальный поиск по коду и Markdown выбранного проекта. PDF/DOCX обрабатываются в основном AI-процессе, здесь не индексируются. Без LLM-запроса и отправки кода внешнему провайдеру. Результаты поиска не подтверждают дефект.</p><form onSubmit={e=>{e.preventDefault();void search()}}><label htmlFor="context-query">Что найти в проекте?</label><div className="context-query-row"><input id="context-query" value={query} maxLength={1000} onChange={e=>setQuery(e.target.value)} placeholder="Например: платёж при точном балансе"/><button className="secondary" disabled={disabled||busy||query.trim().length<2}><Search size={16}/>{busy?'Индексирую и ищу…':'Найти'}</button></div></form>{busy&&<p role="status">Строю локальный индекс и ищу подходящие фрагменты. Первый поиск может занять больше времени.</p>}{error&&<p role="alert" className="alert error">{error}</p>}{result&&<div aria-live="polite"><p>{result.mode==='lexical-fallback'?'Текстовый поиск: локальная embedding-модель недоступна.':'Семантический поиск с локальной моделью.'} Фрагментов в индексе: {result.chunks}.</p>{result.matches.length?result.matches.map((r,i)=><details key={i}><summary>{r.path} · строки {r.start_line}-{r.end_line}</summary><CodeView code={r.content} language={r.path.endsWith('.py')?'python':r.path.endsWith('.md')?'markdown':'typescript'}/></details>):<p>Подходящие фрагменты не найдены. Попробуйте другой запрос.</p>}</div>}</details>
}
