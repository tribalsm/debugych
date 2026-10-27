import {deriveSnapshot} from '../deriveSnapshot.js';
import {resultTarget} from '../resultTarget.js';
import {redactChat} from './privacy.js';
import {type Context,type Snapshot,type Connection,type PageAction,type Run} from '../contracts.js';
export interface ChatSource {label:string;page:PageAction;projectId:string;target:ReturnType<typeof resultTarget>}
export interface Case {name:string;status:string;traceback?:string;test_id?:string}
export interface ChatContext {scope:string;revision:string;projectName:string;projectId:string;rootId?:string;snapshot:Snapshot;connected:boolean;demo:boolean;historical:boolean;receivedAt?:number;original?:Run&{cases?:Case[]};cases:Case[];expected?:string;actual?:string;traceback?:string;description?:string;proposal?:string;changes:{path:string;before:string;after:string}[];plan:{title:string;code:string;gherkin:string}[];requirements:{key:string;text:string;quote:string}[];sources:Partial<Record<PageAction,ChatSource>>}
const clip=(v:unknown,n=1600)=>typeof v==='string'?redactChat(v).slice(0,n):'';
/** Immutable, bounded project/run facts. No generated oracle, eval, or AI claims. */
export class CompanionContextBuilder {
 static build(c:Context,options:{backendUrl:string;connection:Connection;receivedAt?:number}):ChatContext{
  const local:Context={...c,runs:c.runs.filter(r=>r.project_id===c.project.id),bugs:c.bugs.filter(b=>b.project_id===c.project.id),fixes:c.fixes.filter(f=>f.project_id===c.project.id)};
  const snapshot=structuredClone(deriveSnapshot(local));
  const original=local.runs.find(r=>r.id===snapshot.bug?.run_id)??local.runs.find(r=>r.operation==='run'&&(r.id===snapshot.rootId||r.parent_workflow_id===snapshot.rootId));
  const fullBug=snapshot.bug as (typeof snapshot.bug)&{expected?:string;actual?:string;traceback?:string};
  const fullFix=snapshot.fix as (typeof snapshot.fix)&{changes?:{path:string;before:string;after:string}[]};
  const cases=Array.isArray((original as {cases?:Case[]})?.cases)?(original as Run&{cases:Case[]}).cases.slice(0,80).map(v=>({name:clip(v.name,300),status:clip(v.status,30),traceback:clip(v.traceback,1200),test_id:clip(v.test_id,40)})):[];
  const tests=(c.tests??[]).filter(t=>t.project_id===c.project.id&&t.result!=='not_run'&&((original&&t.last_run_id===original.id)||(!original&&t.validation_id===snapshot.rootId)));
  const sources:ChatContext['sources']={};for(const page of snapshot.actions)sources[page]={label:({project:'Проект',proof:'Bug Proof',tests:'Тесты',diff:'Diff',verification:'Fix & Verify',results:'Отчёт'})[page],page,projectId:c.project.id,target:resultTarget(page,snapshot,local)};
  return {scope:[options.backendUrl,c.project.id,snapshot.rootId??'empty'].join('|'),revision:snapshot.key,projectName:clip(c.project.name,150),projectId:c.project.id,rootId:snapshot.rootId,snapshot,connected:options.connection==='connected',demo:c.project.demo,historical:!!c.selectedRunId,receivedAt:options.receivedAt,original:original?structuredClone(original):undefined,cases,expected:clip(fullBug?.expected),actual:clip(fullBug?.actual),traceback:clip(fullBug?.traceback,2500),description:clip(fullBug?.description),proposal:clip(fullFix?.explanation),changes:(fullFix?.changes??[]).slice(0,12).map(v=>({path:clip(v.path,160),before:clip(v.before,2500),after:clip(v.after,2500)})),plan:tests.slice(0,12).map(t=>({title:clip(t.title,200),code:clip(t.code,2500),gherkin:clip(t.gherkin,1800)})),requirements:(c.requirements??[]).filter(r=>r.project_id===c.project.id&&tests.some(t=>t.requirement_id===r.id)).slice(0,12).map(r=>({key:clip(r.key,40),text:clip(r.text,1000),quote:clip(r.quote,1000)})),sources};
 }
}
