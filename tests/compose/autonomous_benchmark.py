"""Two fresh public inputs; no developer correction, proof approval or apply.
Oracle files are read only by independent() AFTER the workflow terminates.
"""
import argparse,json,time
from pathlib import Path
from stack_smoke import request,upload
from fix_verify_smoke import archive
from benchmark import independent
from services.ai.engine import Plan,Scenario
from services.ai.validation import plan_hash

ROOT=Path(__file__).resolve().parents[2]

def terminal(job):
    for _ in range(600):
        r=request('/api/runs/'+job['id'])
        if r['status'] in ('completed','failed','manual_review_required'):return r
        time.sleep(.5)
    raise RuntimeError('Workflow did not terminate within existing worker hard limit')

def evaluate(name):
    pid=request('/api/projects',{'name':'Autonomous fresh control · '+name})['id']
    for path in sorted((ROOT/'evaluation/projects'/name).rglob('*')):
        if path.is_file():upload(pid,path.relative_to(ROOT/'evaluation/projects'/name).as_posix(),path.read_text(encoding='utf-8'))
    before=archive(pid)
    preview=request('/api/projects/'+pid+'/ai-context')
    started=time.monotonic()
    workflow=terminal(request('/api/projects/'+pid+'/autonomous',{'consent':{'confirm':True,
        'project_state_sha256':preview['project_state_sha256'],'provider_fingerprint':preview['provider_fingerprint']}}))
    return collect(name,pid,workflow,before,round(time.monotonic()-started,3))

def collect(name,pid,workflow,before,seconds=None):
    result={'name':name,'project_id':pid,'mode':request('/api/health')['ai_provider_mode'],
        'workflow':workflow,'workflow_seconds':seconds,
        'autonomous':workflow['status']=='completed' and workflow.get('qa_report',{}).get('autonomous') is True,
        'manual_interventions':0,'source_unchanged':archive(pid)==before,'candidates':[],'applied':False,
        'ai_statistics':request('/api/projects/'+pid+'/ai-statistics')}
    if workflow.get('original_run_id'):
        original=request('/api/runs/'+workflow['original_run_id'])
        result['original']={k:original.get(k) for k in ('id','status','cases','passed','failed','errors','coverage','coverage_kind','quality','runtime','image_id')}
        tests=request('/api/projects/'+pid+'/test-cases')
        result['generated_modules']=len(tests)
        reconstructed=Plan.model_validate({'requirements':[{k:r[k] for k in ('key','text')} for r in workflow['requirement_evidence']],
            'scenarios':[{k:t[k] for k in Scenario.model_fields} for t in sorted(tests,key=lambda t:t['scenario_index'])]})
        result['tests_unchanged']=plan_hash(reconstructed)==workflow['validation']['plan_sha256']
        if workflow.get('proof_id'):
            result['proof_replay']=request('/api/runs/'+workflow['proof_id'])['replay']
            result['proof_id']=workflow['proof_id']
        if workflow.get('fix_id'):
            fix=next(f for f in request('/api/projects/'+pid+'/fixes') if f['id']==workflow['fix_id'])
            result['candidates']=[{'fix_id':fix['id'],'verified':fix['verified'],'assessment':fix.get('assessment',{'regressions_absent':False})}]
        result['benchmark']=independent(result)
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('--allow-external',action='store_true');p.add_argument('--output',default='work/autonomous-live.json')
    p.add_argument('--project',action='append',choices=['parcel_cart_v2','team_invoice_v2'])
    args=p.parse_args();status=request('/api/ai/status')
    if status['mode']=='live' and not args.allow_external:raise SystemExit('Synthetic source consent requires --allow-external')
    if status['mode']=='live' and status['model']!='gpt-6-luna':raise SystemExit('Configured model differs; no request sent')
    report={'provider_mode':status['mode'],'model':status['model'],'results':[],'autonomy_verified':False,
        'scope':'At most two workflows, each sharing existing per-job calls/token/USD/deadline limits; no overrides. No manual decisions after start.'}
    output=ROOT/args.output
    for name in args.project or ['parcel_cart_v2','team_invoice_v2']:
        result=evaluate(name);report['results'].append(result)
        print(json.dumps({'name':name,'status':result['workflow']['status'],'autonomous':result['autonomous'],
            'calls':result['ai_statistics']['attempts'],'detected':result.get('benchmark',{}).get('detected')},ensure_ascii=True),flush=True)
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    calls=[c for r in report['results'] for c in r['ai_statistics']['calls']]
    usage=[c['usage'] for c in calls if c.get('usage')]
    report['statistics']={'requests':len(calls),'structured_successes':sum(c['outcome']=='succeeded' for c in calls),
        'request_errors':sum(c['outcome']!='succeeded' for c in calls),'reserved_usd':sum(c['reserved_cost_micro_usd'] for c in calls)/1e6,
        'reported_tokens':sum(u['prompt_tokens']+u['completion_tokens'] for u in usage),'usage_unknown':len(calls)-len(usage),
        'response_models':sorted({c['response_model'] for c in calls if c.get('response_model')}),'billed_usd':None}
    report['autonomy_verified']=len(report['results'])==2 and all(r['autonomous'] and r['source_unchanged'] and r.get('tests_unchanged') and r.get('benchmark',{}).get('fix',{}).get('latest_verified') for r in report['results'])
    assert report['statistics']['reserved_usd']<=2.000001
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')

if __name__=='__main__':main()
