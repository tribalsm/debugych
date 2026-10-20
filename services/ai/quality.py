"""Measured diagnostics, never a test-count score or a correctness certificate."""
from services.ai.engine import FailureAnalyzer


def identities(result):
    return {(str(c['test_id']), c.get('classname',''), c['name']):c for c in result.get('cases',[])}


def evaluate(requirement_ids, tests, result):
    """tests are immutable submission metadata, not the subsequently edited plan.

    Dimension tags are unverified model claims. Even passing assertions do not
    establish that all clauses of their linked requirement were tested.
    """
    required=set(map(str,requirement_ids))
    by_id={str(t['id']):t for t in tests}
    cases=result.get('cases',[])
    keys=[(str(c['test_id']),c.get('classname',''),c['name']) for c in cases]
    valid=(result.get('status')=='completed' and result.get('runtime')=='runsc'
           and len(keys)==len(set(keys)) and all(str(c['test_id']) in by_id for c in cases))
    executed=set(); passing=set(); modules=set(); negatives=set(); infrastructure=0
    for case in cases if valid else []:
        test=by_id[str(case['test_id'])]
        classification=FailureAnalyzer.classify(case)
        if classification=='infrastructure': infrastructure+=1
        if case['status'] not in ('passed','failed') or classification=='infrastructure':continue
        rid=str(test['requirement_id'])
        if rid not in required:continue
        modules.add(str(case['test_id']));executed.add(rid)
        if case['status']=='passed':passing.add(rid)
        if {'negative','invalid_input'} & set(test.get('dimensions',[])):negatives.add(rid)
    # One passing case must not hide a collection/runtime failure in the same
    # generated module. Report partial execution separately.
    partial=modules.copy()
    modules={tid for tid in partial if all(c['status'] in ('passed','failed')
             and FailureAnalyzer.classify(c)!='infrastructure'
             for c in cases if str(c['test_id'])==tid)}
    coverage=result.get('coverage') if valid else None
    totals=(coverage or {}).get('totals',{})
    def measured(covered,total):
        n=totals.get(total);v=totals.get(covered)
        return {'covered':v,'total':n,'ratio':v/n if isinstance(n,int) and n>0 and isinstance(v,int) and 0<=v<=n else None}
    return {'observation_valid':valid,'requirements':{'total':len(required),'exercised':sorted(executed),
                'with_passing_assertions':sorted(passing),'unexercised':sorted(required-executed),
                'exercise_ratio':len(executed)/len(required) if required else None},
            'executable_modules':len(modules),'submitted_modules':len(by_id),
            'partially_executable_modules':len(partial-modules),
            'executable_module_ratio':len(modules)/len(by_id) if by_id else None,
            'infrastructure_cases':infrastructure,'negative_requirements_claimed_and_executed':sorted(negatives),
            'line_coverage':measured('covered_lines','num_statements'),
            'branch_coverage':measured('covered_branches','num_branches'),
            'coverage_kind':result.get('coverage_kind') if valid else None,
            'mutation':{'status':'not_run','score':None},
            'limitations':['Runner observations are produced by untrusted project execution.',
                           'Requirement links and dimension tags are claims; exercise is not semantic completeness.',
                           'Coverage and assertion counts cannot certify correctness. No aggregate quality score.']}


def compare_variant(reference, variant):
    """Independent differential check. Bad reference tests cannot kill mutants."""
    before=identities(reference);after=identities(variant)
    reference_ok=(reference.get('status')=='completed' and reference.get('runtime')=='runsc'
                  and bool(before) and len(before)==len(reference.get('cases',[]))
                  and all(c['status']=='passed' for c in before.values()))
    comparable=(reference_ok and variant.get('status')=='completed' and variant.get('runtime')=='runsc'
                and before.keys()==after.keys() and len(after)==len(variant.get('cases',[]))
                and reference.get('image_id')==variant.get('image_id')
                and reference.get('tests_sha256')==variant.get('tests_sha256')
                and all(c['status'] in ('passed','failed') and FailureAnalyzer.classify(c)!='infrastructure' for c in after.values()))
    changed=[list(k) for k,c in after.items() if comparable and c['status']=='failed']
    return {'eligible':comparable,'detected':bool(changed),'failing_cases':changed,
            'reason':None if comparable else 'reference_failed_or_execution_not_comparable'}
