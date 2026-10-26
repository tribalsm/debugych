/** Desktop Companion links select existing records, never perform operations. */
export type ResultTarget={bug?:string;fix?:string;run?:string;section?:'proof'|'diff'|'verification';error?:string};
const uuid=(s:string)=>/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(s);
export function readResultTarget(hash:string):ResultTarget{
 const q=new URLSearchParams(hash.split('?')[1]||''),t:ResultTarget={};
 for(const key of ['bug','fix','run'] as const){if(q.has(key)){const value=q.get(key)!;if(!uuid(value)||q.getAll(key).length!==1)return{error:'Некорректная ссылка на результат.'};t[key]=value;}}
 if(q.has('section')){const s=q.get('section');if(!['proof','diff','verification'].includes(s||''))return{error:'Неизвестный раздел результата.'};t.section=s as ResultTarget['section'];}
 return t;
}
export function targetError(t:ResultTarget,bugs:{id:string;run_id?:string}[],fixes:{id:string;bug_id:string;verification_id?:string;patch_sha256?:string}[],runs:{id:string;fix_id?:string;patch_sha256?:string}[]):string|undefined{
 if(t.error)return t.error;
 const bug=bugs.find(b=>b.id===t.bug),fix=fixes.find(f=>f.id===t.fix),run=runs.find(r=>r.id===t.run);
 if(t.bug&&!bug||t.fix&&(!fix||t.bug&&fix.bug_id!==t.bug)||t.run&&!run)return 'Результат по ссылке не найден в выбранном проекте. Другой результат автоматически не подставляется.';
 if(t.section==='diff'&&!fix||t.section==='verification'&&(!fix||!run||run.fix_id!==fix.id||(fix.verification_id!==run.id&&(!fix.patch_sha256||run.patch_sha256!==fix.patch_sha256))))return 'Ссылка не соответствует версии исправления или проверке.';
 return undefined;
}
