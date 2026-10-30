export type MetricRun={id:string;operation:string;status:string;created_at?:string;passed?:number;failed?:number;errors?:number;skipped?:number;cases?:{status:string}[]};
export function testingMetrics(runs:MetricRun[],days:number|null=30,now=Date.now()){
 const result={attempts:0,successful:0,pending:0,excluded:0,invalid:0,infrastructure:0,passed:0,failed:0,errors:0,skipped:0,passRate:null as number|null,successRate:null as number|null};
 const seen=new Set<string>();
 for(const run of runs){
  if(run.operation!=='run'||seen.has(run.id))continue;seen.add(run.id);
  if(days!==null){const iso=run.created_at||'';const date=Date.parse(iso&& !/(Z|[+-]\d\d:\d\d)$/.test(iso)?iso+'Z':iso);if(!Number.isFinite(date)||date<now-days*86400000||date>now){result.excluded++;continue}}
  if(['queued','running','analyzing','generating'].includes(run.status)){result.pending++;continue}
  if(!['completed','failed'].includes(run.status)){result.excluded++;continue}
  result.attempts++;
  if(run.status==='failed')result.infrastructure++;
  let counts={passed:run.passed,failed:run.failed,errors:run.errors,skipped:run.skipped};
  let valid=Object.values(counts).every(n=>typeof n==='number'&&Number.isInteger(n)&&n>=0);
  if(run.cases){const measured={passed:0,failed:0,errors:0,skipped:0};valid=true;for(const c of run.cases){if(c.status==='error')measured.errors++;else if(c.status==='passed'||c.status==='failed'||c.status==='skipped')measured[c.status]++;else valid=false}valid=valid&&Object.entries(counts).every(([k,n])=>n===undefined||measured[k as keyof typeof measured]===n);counts=measured}
  if(!valid||Object.values(counts).reduce<number>((s,n)=>s+(n||0),0)===0){result.invalid++;continue}
  result.passed+=counts.passed!;result.failed+=counts.failed!;result.errors+=counts.errors!;result.skipped+=counts.skipped!;
  if(run.status==='completed'&&counts.passed!>0&&counts.failed===0&&counts.errors===0)result.successful++;
 }
 const executed=result.passed+result.failed+result.errors;
 result.passRate=executed?result.passed/executed:null;
 result.successRate=result.attempts?result.successful/result.attempts:null;
 return result;
}
