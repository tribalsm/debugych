import{type Context,type Snapshot,type Run,type Bug,type Fix,type TaskState}from'./contracts.js';
const active=new Set(['queued','analyzing','generating','running']);
const order=(a:Run,b:Run)=>(a.created_at??'').localeCompare(b.created_at??'')||a.id.localeCompare(b.id);
/** Trust only bound proof records. A failed test or an LLM claim is insufficient. */
function proved(b:Bug,runs:Run[],demo:boolean){
 if(!['confirmed','fix_verified'].includes(b.status))return false;
 const original=runs.find(r=>r.id===b.run_id&&r.operation==='run'&&r.status==='completed'&&(r.failed??0)>0&&(r.errors??0)===0);
 if(!original)return false;
 if(demo)return original.trusted_demo===true;
 const proof=runs.find(r=>r.id===b.proof_id&&r.operation==='confirm_proof'&&r.status==='completed'&&r.bug_id===b.id);
 return !!(proof&&b.test_sha256&&proof.review?.test_sha256===b.test_sha256&&proof.review.run_id===original.id&&proof.assessment?.reproduced_again===true&&proof.assessment.requirement_reviewed===true&&proof.assessment.infrastructure_excluded===true);
}
function verified(f:Fix,b:Bug,runs:Run[],demo:boolean){
 const v=runs.find(r=>r.id===f.verification_id&&r.operation==='verify'&&r.fix_id===f.id&&r.bug_id===b.id&&r.status==='completed');
 const a=v?.assessment;
 if(!f.verified||!v||a?.original_fixed!==true||a.regressions_absent!==true||a.all_regression_passed===false||(v.failed??0)>0||(v.errors??0)>0)return;
 if(demo)return v.trusted_demo===true?v:undefined;
 if(v.verified===true&&f.patch_sha256&&v.patch_sha256===f.patch_sha256&&f.proof_id===b.proof_id&&a.all_regression_passed===true)return v;
}
export function deriveSnapshot(c:Context):Snapshot {
 const pid=c.project.id,runs=c.runs.filter(r=>r.project_id===pid).sort(order),bugs=c.bugs.filter(b=>b.project_id===pid),fixes=c.fixes.filter(f=>f.project_id===pid);
 const roots=runs.filter(r=>!r.parent_workflow_id);const root=c.selectedRunId?roots.find(r=>r.id===c.selectedRunId):roots.at(-1);
 const base:Snapshot={state:'idle',key:pid+':idle',project:c.project,title:'Ожидает',explanation:'Нет активной проверки.',phrase:'Ну что, проверим код?',events:[],actions:['project','tests'],trustedDemo:c.project.demo};
 if(!root)return c.selectedRunId?{...base,title:'Запуск не найден',explanation:'Выбранный запуск отсутствует в этом проекте.'}:base;
 const family=new Set([root.id]);for(let changed=true;changed;){changed=false;for(const r of runs)if(r.parent_workflow_id&&family.has(r.parent_workflow_id)&&!family.has(r.id)){family.add(r.id);changed=true;}}
 const related=runs.filter(r=>family.has(r.id));const job=[...related].reverse().find(r=>active.has(r.status))??related.at(-1)!;
 const bug=bugs.find(b=>proved(b,runs,c.project.demo)&&((b.run_id&&family.has(b.run_id))||related.some(r=>r.bug_id===b.id)));
 const fix=bug?fixes.filter(f=>f.bug_id===bug.id&&(!c.selectedRunId||related.some(r=>r.fix_id===f.id||r.id===f.verification_id))&&(!(job.fix_id||bug.current_fix_id)||(job.fix_id||bug.current_fix_id)===f.id)).sort((a,b)=>(a.created_at??'').localeCompare(b.created_at??'')).at(-1):undefined;
 const verification=bug&&fix&&fix.verification_id&&family.has(fix.verification_id)?verified(fix,bug,runs,c.project.demo):undefined;
 const result:Snapshot={...base,rootId:root.id,run:job,bug,fix,verification,key:[pid,root.id,job.id,job.status,job.stage,bug?.id,bug?.status,fix?.id,fix?.verified,fix?.applied,verification?.id].join(':'),actions:['project','tests','results',...(bug?['proof' as const]:[]),...(fix?['diff' as const,'verification' as const]:[])]};
 if(root.operation==='analyze'&&root.status==='completed')result.events.push({kind:'analysis_done',key:root.id+':analysis_done',title:'Анализ завершён'});
 if(bug)result.events.push({kind:'bug_found',key:bug.id+':proof:'+(bug.proof_id??bug.run_id),title:'Подтверждён дефект: '+bug.title});
 if(fix)result.events.push({kind:'patch_ready',key:fix.id+':patch:'+(fix.patch_sha256??fix.created_at),title:'Исправление подготовлено, применение отдельно'});
 if(verification)result.events.push({kind:'verification',key:verification.id+':verified',title:fix?.applied?'Проверенный патч применён с подтверждением':'Исправление прошло проверку, патч ещё не применён'});
 if(active.has(job.status)){
  let state:TaskState='idle';const phase=job.stage;
  if(job.status==='queued')return{...result,title:'Задание в очереди',explanation:'Backend ещё не начал выполнение.'};
  if(job.operation==='verify'||phase==='fix_verification')state='verifying';
  else if(job.operation==='propose_fix'||phase==='patch_generation')state='fixing';
  else if(['run','confirm_proof'].includes(job.operation)||['execution','bug_proof'].includes(phase??''))state='testing';
  else if(job.status==='generating'||['generation','semantic_validation','technical_validation','persist_validated_plan'].includes(phase??''))state='generating';
  else if(job.status==='analyzing'||job.operation==='analyze'||phase==='context')state='analyzing';
  const texts:Record<TaskState,[string,string]>={idle:['Выполняется задание','Backend не сообщает различимую стадию.'],analyzing:['Анализ проекта','Так, посмотрим, что тут у нас...'],generating:['Генерация проверок','Готовлю проверки'],testing:['Выполнение тестов','Запускаю тесты'],fixing:['Подготовка исправления','Готовлю исправление. Потом проверим'],verifying:['Независимая проверка','Проверяю, не сломалось ли что-нибудь ещё'],success:['',''],bug_found:['',''],offline:['',''],error:['','']};
  return{...result,state,title:texts[state][0],phrase:texts[state][1],explanation:'Фактическое состояние backend: '+job.operation+' / '+job.status+(phase?' / '+phase:'')};
 }
 if(root.status==='failed'||job.status==='failed'||(job.errors??0)>0){result.events=result.events.filter(e=>e.kind!=='verification');result.events.push({kind:'execution_error',key:job.id+':error',title:'Ошибка выполнения задания'});return{...result,state:'error',title:'Ошибка выполнения',phrase:'Проверка прервалась',explanation:job.error?.slice(0,600)??'Сбой выполнения не подтверждает дефект пользовательского кода.'};}
 if([root.status,job.status].includes('manual_review_required'))return{...result,title:'Нужна ручная проверка',explanation:'Изучите доказательства и ожидания в основном приложении.'};
 if(verification)return{...result,state:'success',title:'Исправление прошло проверку',phrase:'Исправление прошло проверку!',explanation:fix?.applied?'Backend сообщает о применении с отдельным подтверждением. Полная корректность проекта не доказана.':'Конкретный патч проверен. Патч ещё не применён. Полная корректность проекта не доказана.'};
 if(fix)return{...result,title:'Исправление подготовлено',phrase:'Готово предложение. Применение отдельно',explanation:job.operation==='verify'?'Проверка не подтвердила исправление. Изучите результат в Fix & Verify.':'Подготовленный diff ещё не означает успешной проверки или применения.'};
 if(bug)return{...result,state:'bug_found',title:'Подтверждена ошибка',phrase:'Ага, попался!'+(bug.file?' Ошибка в '+bug.file:''),explanation:[bug.title,bug.description,bug.file?bug.file+(bug.line?':'+bug.line:''):''].filter(Boolean).join('\n')};
 return{...result,title:job.status==='completed'?'Результат готов':'Неизвестное состояние',explanation:(job.failed??0)>0?'Тесты выявили отклонения. Подтверждённого Bug Proof для этого запуска нет.':'Статус: '+job.status+'. Успех всего проекта не заявляется.'};
}
export const animationFor=(state:TaskState)=>({idle:'idle',analyzing:'analyzing',generating:'analyzing',testing:'testing',bug_found:'bug_found',fixing:'fixing',verifying:'testing',success:'success',error:'error',offline:'idle'}[state]);
