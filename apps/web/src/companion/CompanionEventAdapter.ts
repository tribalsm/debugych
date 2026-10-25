import type {AgentState} from '../MascotSlot';
export type CompanionRun={id:string;project_id?:string;created_at?:string;status:string;operation:string;stage?:string;parent_workflow_id?:string;bug_id?:string;fix_id?:string;verification_id?:string;patch_sha256?:string;verified?:boolean;passed?:number;failed?:number;errors?:number;error?:string;assessment?:{original_fixed?:boolean;regressions_absent?:boolean;all_regression_passed?:boolean};qa_report?:{autonomous:boolean}};
export type CompanionBug={id:string;project_id?:string;run_id?:string;current_fix_id?:string;status:string;title:string;expected:string;actual:string;description:string;traceback:string;steps:string[]};
export type CompanionFix={id:string;project_id?:string;bug_id:string;diff:string;explanation:string;verified:boolean;verification_id?:string;patch_sha256?:string;assessment?:{original_fixed?:boolean;regressions_absent?:boolean;all_regression_passed?:boolean}|null};
export type CompanionContext={project?:{id:string;name:string;demo:boolean};runs:readonly CompanionRun[];bugs:readonly CompanionBug[];fixes:readonly CompanionFix[];ready:boolean;networkError?:string;requirementCount:number;testCount:number};
export type CompanionSnapshot={state:AgentState;key:string;projectId:string;projectName:string;runId?:string;workflowId?:string;bug?:CompanionBug;fix?:CompanionFix;run?:CompanionRun;title:string;explanation:string;demo:boolean;canVerify:boolean;requirementCount:number;testCount:number};
const active=new Set(['queued','analyzing','generating','running']);
/** Derive facts from one committed project snapshot. No HTTP, timer, inferred bug, or approval. */
export function CompanionEventAdapter(c:CompanionContext):CompanionSnapshot{
 const project=c.project,projectId=project?.id??'';
 const base:CompanionSnapshot={state:'idle',key:projectId+':idle',projectId,projectName:project?.name??'Проект не выбран',title:'Ну что, проверим твой код?',explanation:'Выберите проект. Доказательства и результаты появятся после реальных проверок.',demo:project?.demo??false,canVerify:false,requirementCount:c.requirementCount,testCount:c.testCount};
 if(!project)return base;
 if(c.networkError)return {...base,state:'error',key:projectId+':connection-error',title:'Проверка прервалась',explanation:'Не удалось получить актуальные данные. Успех и найденный баг не подтверждены.'};
 if(!c.ready)return {...base,key:projectId+':loading',title:'Загружаю данные проекта',explanation:'Ожидаю подтверждённое состояние backend.'};
 const runs=c.runs.filter(r=>r.project_id===projectId),bugs=c.bugs.filter(b=>b.project_id===projectId),fixes=c.fixes.filter(f=>f.project_id===projectId);
 const ordered=[...runs].sort((a,b)=>a.created_at&&b.created_at?a.created_at.localeCompare(b.created_at):0);
 const roots=ordered.filter(r=>!r.parent_workflow_id),root=roots.at(-1);
 if(!root)return {...base,title:'Готов к работе',explanation:`В проекте ${c.requirementCount} требований и ${c.testCount} тестов. Выберите следующий шаг в рабочей области.`};
 const familyIds=new Set([root.id]);let changed=true;while(changed){changed=false;for(const r of runs)if(r.parent_workflow_id&&familyIds.has(r.parent_workflow_id)&&!familyIds.has(r.id)){familyIds.add(r.id);changed=true}}
 const family=ordered.filter(r=>familyIds.has(r.id)),job=[...family].reverse().find(r=>active.has(r.status))??family.at(-1)??root;
 const relatedBugs=bugs.filter(b=>['confirmed','fix_verified'].includes(b.status)&&(!!b.run_id&&familyIds.has(b.run_id)||family.some(r=>r.bug_id===b.id)));
 const bug=relatedBugs.find(b=>b.id===job.bug_id)??relatedBugs[0];
 const fix=bug?[...fixes].reverse().find(f=>f.bug_id===bug.id&&(!(job.fix_id||bug.current_fix_id)||(job.fix_id||bug.current_fix_id)===f.id)):undefined;
 const doneVerification=fix?family.find(v=>v.id===fix.verification_id&&v.operation==='verify'&&v.fix_id===fix.id&&v.bug_id===bug?.id&&v.status==='completed'&&v.verified!==false&&(!fix.patch_sha256||v.patch_sha256===fix.patch_sha256)):undefined;
 const assessment=doneVerification?.assessment??fix?.assessment;
 const verified=!!(fix?.verified&&doneVerification&&assessment?.original_fixed===true&&assessment.regressions_absent===true&&assessment.all_regression_passed!==false);
 const common={...base,runId:job.id,workflowId:root.id,run:job,bug,fix,canVerify:!!bug&&!!fix&&!fix.verified&&!family.some(r=>active.has(r.status)),key:[projectId,root.id,job.id,job.status,job.stage,bug?.id,bug?.status,fix?.id,fix?.patch_sha256,fix?.verification_id,verified].join(':')};
 if(active.has(job.status)){
  const phase=job.stage??job.operation;let state:AgentState='analyzing';
  if(['patch_generation','fix_verification'].includes(phase)||['propose_fix','verify'].includes(job.operation))state='fixing';
  else if(['execution','bug_proof'].includes(phase)||['run','confirm_proof'].includes(job.operation))state='testing';
  else if(/generat/.test(phase)||job.status==='generating')state='generating';
  const copy:Record<string,[string,string]>={analyzing:['Так, посмотрим, что тут у нас...','Backend анализирует требования и проект.'],generating:['Придумываю, как проверить твой код','Backend формирует сценарии и исполняемые тесты.'],testing:['Проверяю, что действительно работает','Выполняются тесты или повторное воспроизведение. Победа пока не подтверждена.'],fixing:['Попробую исправить. Потом обязательно проверю','Backend готовит патч или проверяет конкретную версию исправления.']};
  return {...common,state,title:copy[state][0],explanation:copy[state][1]};
 }
 if(root.status==='failed'||job.status==='failed'||(job.errors??0)>0)return {...common,state:'error',title:'Хм. Проверка прервалась',explanation:job.error??'Есть ошибка выполнения. Она сама по себе не подтверждает дефект приложения.'};
 if(root.status==='manual_review_required'||job.status==='manual_review_required')return {...common,state:'idle',title:'Нужна проверка ожиданий',explanation:'Автоматическая проверка остановилась. Изучите результат в рабочей области.'};
 if(verified)return {...common,state:'success',title:'Вот теперь другое дело!',explanation:'Конкретный патч прошёл проверку исходной ошибки и регрессии. Полная корректность проекта не доказана.'};
 if(bug)return {...common,state:'bug_found',title:'Ага, попался!',explanation:`Подтверждён дефект: ${bug.title}. Доказательство доступно в Bug Lab.`};
 return {...common,state:'idle',title:'Результат готов',explanation:(job.failed??0)>0?'Есть отклонения в тестах, но Bug Proof ещё не подтвердил дефект.':job.operation==='analyze'?`План готов: ${c.requirementCount} требований, ${c.testCount} тестов.`:'Проверенный набор завершён. Это не доказательство полной корректности проекта.'};
}
export function explainCompanion(s:CompanionSnapshot,question:'current'|'proof'|'diff'|'results'){
 if(question==='proof')return s.bug?`${s.bug.description}\nОжидалось: ${s.bug.expected}\nПолучено: ${s.bug.actual}\n${s.bug.steps.join('\n')}`:'Для текущего запуска нет подтверждённого Bug Proof.';
 if(question==='diff')return s.fix?`${s.fix.explanation}\n\n${s.fix.diff}`:'Для текущего запуска ещё нет подготовленного патча.';
 if(question==='results')return s.run?`Задание ${s.run.id}: ${s.run.status}.\nУспешно: ${s.run.passed??'нет измерения'}, отклонений: ${s.run.failed??'нет измерения'}, ошибок выполнения: ${s.run.errors??0}.\n${s.explanation}`:'Результаты текущего запуска ещё не получены.';
 return s.explanation;
}
