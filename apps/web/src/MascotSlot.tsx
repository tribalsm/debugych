import type {ReactNode} from 'react';
import {Activity, ShieldCheck} from 'lucide-react';

export type AgentState='idle'|'analyzing'|'generating'|'testing'|'bug_found'|'fixing'|'success'|'error';
type Job={status:string;operation:string;stage?:string;parent_workflow_id?:string;qa_report?:{autonomous:boolean};verified?:boolean};
export function agentState(jobs:Job[],bugs:{status:string}[]):AgentState{
 const active=[...jobs].reverse().find(j=>['queued','analyzing','generating','running'].includes(j.status));
 if(active){const phase=active.stage||active.operation;if(/verify|fix/.test(phase))return 'fixing';if(/run|test|proof/.test(phase))return 'testing';if(/generat/.test(phase)||active.status==='generating')return 'generating';return 'analyzing'}
 const latest=jobs[jobs.length-1];
 const terminal=latest?.parent_workflow_id?jobs.find(j=>(j as Job&{id?:string}).id===latest.parent_workflow_id)||latest:latest;
 if(terminal?.status==='failed')return 'error';
 if(terminal?.status==='manual_review_required')return 'idle';
 if(terminal?.status==='completed'&&(terminal.verified===true||terminal.qa_report?.autonomous&&bugs.some(b=>b.status==='fix_verified')))return 'success';
 if(bugs.some(b=>b.status==='confirmed'))return 'bug_found';return 'idle';
}
const copy:Record<AgentState,[string,string]>={idle:['Готов к работе','Загрузите проект и требования, чтобы начать проверку.'],analyzing:['Изучаю требования','Ожидания формируются по документам проекта.'],generating:['Готовлю тесты','Тестовый план, Gherkin и исполняемый код.'],testing:['Выполняю проверки','Результаты поступают из Test Runner.'],bug_found:['Дефект подтверждён','Откройте Bug Lab: там требование и доказательство.'],fixing:['Проверяю исправление','Изолированная копия, исходные тесты и регрессия.'],success:['Исправление проверено','Применение к оригиналу требует отдельного подтверждения.'],error:['Проверка остановлена','Изучите ошибку задания. Это не подтверждение дефекта.']};
/** UI-owned extension point. Renderer owns all model loading and disposal. */
export function MascotSlot({state,compact=false,reducedMotion=false,children}:{state:AgentState;compact?:boolean;reducedMotion?:boolean;children?:ReactNode}){return <section className={'agent-slot '+(compact?'compact':'')} data-agent-state={state} data-reduced-motion={reducedMotion} aria-label="Статус AI-агента">{!compact&&<div className="mascot-viewport">{children||<div className="agent-signature"><ShieldCheck size={32}/><span>Требование → доказательство</span><small>Каждый вывод можно проверить</small></div>}</div>}<div className="agent-status"><Activity size={17}/><div><strong>{copy[state][0]}</strong><p>{copy[state][1]}</p></div></div></section>}
