import {CompanionRequestError} from './RequestErrors.js';
import{uuid}from'../contracts.js';
import{type ChatContext,type ChatSource}from'./CompanionContextBuilder.js';
import{type ChatAnswer}from'./StructuredAnswers.js';
export interface AIPreview {available:boolean;provider:string;model:string;max_reserved_usd:number;max_calls:number;context_sha256:string;provider_fingerprint:string;context:unknown;notice:string;characters:number}
export type ConfirmAI=(p:AIPreview,signal:AbortSignal)=>Promise<boolean>;
export interface AITransport {post:(path:string,body:unknown,signal:AbortSignal)=>Promise<unknown>}
const sha=(v:unknown)=>typeof v==='string'&&/^[0-9a-f]{64}$/.test(v);
/** Server-only model access, one preview and one explicitly confirmed POST. No retries. */
export class CompanionAIClient {
 constructor(private transport:AITransport){}
 async explain(question:string,c:ChatContext,signal:AbortSignal,confirm:ConfirmAI):Promise<ChatAnswer>{
  if(!c.connected||!c.rootId||!uuid(c.projectId)||!uuid(c.rootId))throw Error('Нет доступного контекста backend');
  const body={request_id:crypto.randomUUID(),project_id:c.projectId,root_run_id:c.rootId,bug_id:c.snapshot.bug?.id??null,fix_id:c.snapshot.fix?.id??null,question};
  const p=await this.transport.post('/api/companion/preview',body,signal) as AIPreview;
  if(signal.aborted)throw new DOMException('Aborted','AbortError');
  if(!p?.available)throw Error('AI-объяснения недоступны в backend');
  if(!sha(p.context_sha256)||!sha(p.provider_fingerprint)||p.max_calls!==1||typeof p.max_reserved_usd!=='number'||p.max_reserved_usd<=0||p.max_reserved_usd>.25||!Number.isInteger(p.characters)||p.characters>18000||typeof p.provider!=='string'||typeof p.model!=='string')throw new CompanionRequestError('invalid');
  if(!await confirm(p,signal)||signal.aborted)throw new DOMException('Отправка отменена','AbortError');
  const result=await this.transport.post('/api/companion/ask',{...body,confirm:true,context_sha256:p.context_sha256,provider_fingerprint:p.provider_fingerprint},signal) as {kind?:string;text?:string;hypotheses?:string[];sources?:ChatSource[];project_id?:string;root_run_id?:string;context_sha256?:string;notice?:string};
  if(signal.aborted)throw new DOMException('Aborted','AbortError');
  if(result.kind!=='llm'||result.project_id!==c.projectId||result.root_run_id!==c.rootId||result.context_sha256!==p.context_sha256||typeof result.text!=='string'||result.text.length>4000||!Array.isArray(result.hypotheses)||result.hypotheses.some(h=>typeof h!=='string'||h.length>800)||!Array.isArray(result.sources))throw new CompanionRequestError('invalid','Ответ не связан с этим вопросом');
  const sources:ChatSource[]=[];for(const s of result.sources){if(!s||typeof s.label!=='string'||s.label.length>40||s.projectId!==c.projectId||!['project','proof','tests','diff','verification','results'].includes(s.page)||!s.target||Object.values(s.target).some(id=>id!==undefined&&!uuid(id)))throw new CompanionRequestError('invalid');sources.push({projectId:s.projectId,page:s.page,label:s.label.slice(0,40),target:s.target});}
  const authoritative=c.snapshot.fix?`\n\nДанные backend: патч ${c.snapshot.fix.applied?'применён':'не применён'}; успешная связанная проверка ${c.snapshot.verification?'подтверждена':'не подтверждена'}.`:'';
  return {kind:'llm',text:result.text+(result.hypotheses.length?'\n\nГипотезы, требующие проверки:\n'+result.hypotheses.join('\n'):'')+authoritative,sources,scope:c.scope,revision:c.revision};
 }
}
