"""Blind-input workflow harness. Oracle stays on evaluator host, never uploaded."""
import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request
from stack_smoke import request,upload,wait,BASE
from fix_verify_smoke import archive,propose,verify

ROOT=Path(__file__).resolve().parents[2]

class WorkflowFailure(RuntimeError):
    def __init__(self,pid,cause):
        self.project_id=pid
        self.cause_type=type(cause).__name__
        super().__init__('Control workflow failed; inspect its safe audit metadata')


def evaluate(name,mode):
    pid=request('/api/projects',{'name':'Independent control · '+name})['id']
    try:return evaluate_project(name,mode,pid)
    except Exception as error:raise WorkflowFailure(pid,error) from None


def evaluate_project(name,mode,pid):
    folder=ROOT/'evaluation/projects'/name
    uploaded=[]
    for path in sorted(folder.rglob('*')):
        if path.is_file():
            relative=path.relative_to(folder).as_posix()
            upload(pid,relative,path.read_text(encoding='utf-8'));uploaded.append(relative)
    assert all('oracle' not in name for name in uploaded)
    analysis=wait(request(f'/api/projects/{pid}/analyze',{}))
    tests=request(f'/api/projects/{pid}/test-cases')
    before=archive(pid)
    original=wait(request(f'/api/projects/{pid}/runs',{}))
    bugs=request('/api/bugs?project_id='+pid)
    result={'name':name,'project_id':pid,'mode':mode,'uploaded_files':uploaded,'analysis_id':analysis['id'],'requirement_evidence':analysis.get('requirement_evidence',[]),
            'original':{k:original.get(k) for k in ('id','status','cases','passed','failed','errors','coverage','coverage_kind','quality','runtime','image_id')},
            'generated_modules':len(tests),'findings':len(bugs),'candidates':[],'applied':False}
    reproduced=[b for b in bugs if b['status']=='reproduced']
    if mode=='live':
        result['pending_user_review']=True
        result['ai_statistics']=request(f'/api/projects/{pid}/ai-statistics')
        return result
    if reproduced:
        bug=reproduced[0]
        proof=wait(request(f"/api/bugs/{bug['id']}/confirm-proof",{'confirm_expectation':True,'reviewer_note':'Synthetic control review: assertion сверено с документом требований и независимой спецификацией контрольного проекта.',
                    'run_id':original['id'],'test_sha256':bug['test_sha256']}))
        result['bug_id']=bug['id'];result['proof_id']=proof['id']
        result['proof_replay']={k:proof['replay'].get(k) for k in ('status','cases','runtime','image_id')}
        proposed=wait(request(f"/api/bugs/{bug['id']}/propose-fix",{}))
        fix=next(f for f in request(f'/api/projects/{pid}/fixes') if f['id']==proposed['fix_id'])
        checked=verify(bug,fix)
        result['candidates'].append({'fix_id':fix['id'],'verification_id':checked['id'],'verified':checked['verified'],'assessment':checked['assessment']})
        assert archive(pid)==before,'Original changed without approval'
        assert [t['code'] for t in request(f'/api/projects/{pid}/test-cases')]==[t['code'] for t in tests]
        result['tests_unchanged']=True;result['source_unchanged']=True
    result['ai_statistics']=request(f'/api/projects/{pid}/ai-statistics')
    return result

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',default='work/novel-contract-results.json')
    parser.add_argument('--allow-external',action='store_true',help='Explicit approval to send only these control projects to configured live provider')
    args=parser.parse_args()
    health=request('/api/health')
    if not health['ai_available']:
        report={'live_ai_status':'NOT_VERIFIED_API_KEY_MISSING','live_generations':0,'results':[]}
    else:
        mode=health['ai_provider_mode']
        if mode=='live' and not args.allow_external:
            raise SystemExit('Live sending requires --allow-external. Review control project files first.')
        if mode=='live':
            import stack_smoke
            stack_smoke.ALLOW_LIVE_TEST_TRANSPORT=True
        report={'live_ai_status':'NOT_VERIFIED_CONTRACT_ONLY' if mode=='contract-test' else 'LIVE_ATTEMPTED','results':[]}
        for name in ('python_dispatch','react_booking'):
            try:report['results'].append(evaluate(name,mode))
            except Exception as error:
                # Never include provider messages or sensitive body in evaluation logs.
                report['results'].append({'name':name,'mode':mode,'workflow_error_type':type(error).__name__})
        # Ground truth read only AFTER sending and execution; never provider input.
        oracle=json.loads((ROOT/'evaluation/oracles.json').read_text(encoding='utf-8'))
        report['known_defects']=oracle
        report['notice']='Contract provider uses prepared responses. These results validate infrastructure, not autonomous AI discovery. Independent evaluation is separate: benchmark.py.'
    path=ROOT/args.output
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':report['live_ai_status'],'projects':len(report['results']),'workflow_errors':sum('workflow_error_type' in r for r in report['results'])}))
    if any('workflow_error_type' in r for r in report['results']):raise SystemExit(1)

if __name__=='__main__':main()
