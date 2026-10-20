"""Evidence-bound semantic review plus mandatory isolated syntax/discovery.

No application execution results or evaluator data may enter semantic review.
Passing discovery is never evidence that an expectation agrees with a document.
"""
import ast
import hashlib
import json
import re
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from services.ai.engine import Plan,TestPlanner,scenario_schema
from services.ai.adapter import AIError


def plan_hash(plan):
    return hashlib.sha256(json.dumps(plan.model_dump(),sort_keys=True,ensure_ascii=False).encode()).hexdigest()


class Assessment(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario: int = Field(ge=0,le=39)
    verdict: Literal['supported','contradiction','ambiguous','invalid_test']
    requirement_quote: str = Field(min_length=1,max_length=2000)
    assertion_indexes: list[int] = Field(min_length=1,max_length=80)
    rationale: str = Field(min_length=1,max_length=600)


class SemanticReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assessments: list[Assessment] = Field(min_length=1,max_length=40)

class Counterargument(BaseModel):
    model_config=ConfigDict(extra='forbid')
    scenario: int = Field(ge=0,le=39)
    disputed_claim: str = Field(min_length=1,max_length=600)
    code_quote: str = Field(min_length=1,max_length=1200)
    requirement_quote: str = Field(min_length=1,max_length=2000)
    rationale: str = Field(min_length=1,max_length=600)

class Adjudication(SemanticReview):
    counterarguments: list[Counterargument] = Field(max_length=40)


class ManualReview(AIError):
    def __init__(self,kind='requirement_ambiguity'):
        self.kind=kind
        super().__init__('manual_review_required')


def assertions(code,framework):
    if framework=='pytest':
        tree=ast.parse(code)
        result=[ast.get_source_segment(code,n) for n in ast.walk(tree) if isinstance(n,ast.Assert)]
        result += [ast.get_source_segment(code,n) for n in ast.walk(tree) if isinstance(n,ast.With)
                   and any(isinstance(i.context_expr,ast.Call) and isinstance(i.context_expr.func,ast.Attribute)
                           and i.context_expr.func.attr in ('raises','warns') for i in n.items)]
    else:
        # Evidence excerpts, not a JavaScript parser. esbuild + actual Playwright
        # discovery run independently in gVisor before semantic acceptance.
        result=[line.strip() for line in code.splitlines() if re.search(r'\bexpect\s*\(',line)]
    if not result or len(result)>80:raise ValueError('assertions_required')
    return result


def static_check(plan):
    """Conservative preflight policy, never a replacement for gVisor."""
    for scenario in plan.scenarios:
        code=scenario.code
        if scenario.framework=='pytest':
            try:tree=ast.parse(code)
            except SyntaxError:return 'syntax_error'
            modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            modules += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
            if any(m.split('.')[0] in {'subprocess','socket','ctypes','multiprocessing','requests','urllib'} for m in modules):return 'unsafe_test'
            for n in ast.walk(tree):
                if isinstance(n,ast.Assert) and not any(isinstance(v,(ast.Name,ast.Call,ast.Attribute)) for v in ast.walk(n.test)):return 'invalid_test'
                if isinstance(n,ast.Call):
                    name=ast.unparse(n.func)
                    if name in ('eval','exec','compile','__import__','open') or name.startswith(('os.','sys.','shutil.')):return 'unsafe_test'
                if isinstance(n,ast.FunctionDef) and n.name.startswith('test') and any(isinstance(a,ast.Pass) for a in n.body):return 'invalid_test'
            if re.search(r'pytest\.mark\.(skip|xfail)|pytest\.(skip|xfail)\(',code):return 'invalid_test'
        else:
            if re.search(r'(?:node:)?(?:child_process|worker_threads)|\beval\s*\(|new\s+Function\b|process\.(?:env|exit)|require\s*\(|(?:from\s*[\'"](?:node:)?(?:fs|net|http|https|vm))',code):return 'unsafe_test'
            if re.search(r'test\.(?:skip|fixme|fail|only)\s*\(',code):return 'invalid_test'
            if re.search(r'\bexpect\s*\(\s*(?:true|false|null|\d+)\s*\)',code):return 'invalid_test'
            for url in re.findall(r'(?:goto|fetch)\s*\(\s*[\'"]([^\'"]+)',code):
                if not url.startswith('/') and not url.startswith('http://127.0.0.1:4173/'):return 'unsafe_test'
        try:assertions(code,scenario.framework)
        except (ValueError,SyntaxError):return 'invalid_test'
    return None

def execution_issue(result):
    """A missing/ambiguous locator cannot automatically prove a product bug."""
    if result.get('status')!='completed' or result.get('runtime')!='runsc':return 'infrastructure_error'
    for case in result.get('cases',[]):
        trace=case.get('traceback','')
        if any(marker in trace for marker in ('element(s) not found','strict mode violation','resolved to 0 elements')):
            return 'test_binding_ambiguity'
        if case['status']=='skipped':return 'invalid_test'
        if case['status']=='error':return 'infrastructure_or_test_error'
    return None


def check_review(value,plan,evidence,documents=None):
    if sorted(a.scenario for a in value.assessments)!=list(range(len(plan.scenarios))):raise ValueError('Review coverage')
    quotes={r.key:(documents.get(r.source,r.quote) if documents else r.quote) for r in evidence}
    for a in value.assessments:
        s=plan.scenarios[a.scenario]
        if a.requirement_quote not in quotes[s.requirement]:raise ValueError('Review quote ungrounded')
        expected=list(range(len(assertions(s.code,s.framework))))
        if sorted(a.assertion_indexes)!=expected:raise ValueError('Review omitted assertions')
    return value

def check_adjudication(value,plan,evidence,prior,documents=None):
    check_review(value,plan,evidence,documents)
    rejected={a.scenario:a for a in prior.assessments if a.verdict!='supported'}
    if all(a.verdict=='supported' for a in value.assessments):
        if sorted(c.scenario for c in value.counterarguments)!=sorted(rejected):raise ValueError('Missing independent counterarguments')
    quotes={r.key:(documents.get(r.source,r.quote) if documents else r.quote) for r in evidence}
    for c in value.counterarguments:
        if c.scenario not in rejected or c.disputed_claim not in rejected[c.scenario].rationale:raise ValueError('Ungrounded disputed claim')
        s=plan.scenarios[c.scenario]
        if c.code_quote not in s.code or c.requirement_quote not in quotes[s.requirement]:raise ValueError('Ungrounded counterevidence')
    return value


class LayeredValidator:
    def __init__(self,execute):
        self.execute=execute
        self.report={'version':1,'status':'pending','attempts':[],'repairs':0,'manual_interventions':0}

    def __call__(self,plan,files,evidence,adapter):
        from services.runner.contracts import SandboxJob
        docs=[r.model_dump() for r in evidence]
        documents={n:t for n,t in files if n.lower().endswith(('.md','.pdf','.docx'))}
        def semantic(operation,prior=None):
            context={'operation':operation,'requirements':docs,'original_documents':[{'path':n,'content':t} for n,t in documents.items()],
                'scenarios':[{'index':i,'requirement':s.requirement,'gherkin':s.gherkin,'code':s.code,
                              'assertions':[{'index':j,'code':a} for j,a in enumerate(assertions(s.code,s.framework))]} for i,s in enumerate(plan.scenarios)]}
            if prior:
                context['disputed_review']=prior.model_dump()
                context['technical_facts']={'syntax':'passed','discovery':'passed','case_count':len(self.report['technical']['validation']['collected'])}
            limit=adapter.settings.output_tokens
            try:
                adapter.settings.output_tokens=min(limit,1800)
                def grounded_review(value):
                    self.report.setdefault('semantic_responses',[]).append({'operation':operation,'response':value.model_dump()})
                    return check_adjudication(value,plan,evidence,prior,documents) if prior else check_review(value,plan,evidence,documents)
                return adapter.generate(operation,Adjudication if prior else SemanticReview,
                    'Independently verify EVERY assertion against the original quoted requirements, without implementation or product results. '
                    'For EVERY scenario cite an exact nonempty substring of its original source document and list ALL provided zero-based assertion indexes. '
                    'The extracted requirement.quote may be only an excerpt; check other clauses in original_documents before declaring an expectation undocumented. '
                    'supported means every expectation is justified by the document; contradiction means a specific assertion conflicts with it; ambiguous means an expectation is undocumented or the specification is unclear; invalid_test means an executable error. '
                    'Give a concise concrete rationale, not hidden reasoning. Do not invent requirements, require exhaustive domain enumeration, or require a particular illustrative sequence. '
                    'Evaluate setup transitions arithmetically. A qualified CSS selector is allowed even when business requirements do not describe DOM. '
                    'If a prior reviewer is supplied, independently test its arguments against quoted facts; neither discovery nor prior approval proves semantic correctness. '
                    'When overturning rejection, provide a counterargument for EACH disputed scenario, quoting the exact prior rationale, exact test code and exact requirement text that refute it. '
                    'Never approve merely to resolve a disagreement. Unresolvable ambiguity must remain ambiguous.',
                    context,grounded_review)
            finally:adapter.settings.output_tokens=limit

        for revision in range(2):
            TestPlanner.validate(plan,require_all=True,check_syntax=False)
            kind=static_check(plan)
            technical=None
            if not kind:
                suffixes=('.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css','.json') if plan.scenarios[0].framework=='playwright' else ('.py',)
                job=SandboxJob(id=uuid4(),phase='validate',profile='playwright' if plan.scenarios[0].framework=='playwright' else None,
                    files=[{'path':n,'content':t} for n,t in files if n.endswith(suffixes)],
                    tests=[{'id':uuid4(),'requirement_id':uuid4(),'code':s.code} for s in plan.scenarios])
                technical=self.execute(job.model_dump(mode='json',exclude_none=True))
                self.report['technical']=technical
                self.report['technical_test_ids']=[str(t.id) for t in job.tests]
                check=technical.get('validation') or {}
                observed={str(c['test_id']) for c in check.get('collected',[])}
                valid=(technical.get('status')=='completed' and technical.get('runtime')=='runsc'
                    and technical.get('snapshot_sha256')==job.fingerprint()
                    and check.get('syntax') is True and check.get('discovery') is True
                    and observed=={str(t.id) for t in job.tests}
                    and len({(str(c['test_id']),c['name']) for c in check.get('collected',[])})==len(check.get('collected',[])))
                if not valid:kind=check.get('kind') if check.get('kind') in ('syntax_error','invalid_test') else 'infrastructure_error'
            attempt={'plan_sha256':plan_hash(plan),'technical_kind':kind or 'valid'}
            attempt['draft']=plan.model_dump()
            self.report['attempts'].append(attempt)
            if kind in ('unsafe_test','infrastructure_error'):
                self.report.update(status='manual_review_required',classification=kind);raise ManualReview(kind)
            if not kind:
                first=semantic('validate_semantics')
                attempt['review']=first.model_dump()
                if all(a.verdict=='supported' for a in first.assessments):
                    self.report.update(status='validated',plan_sha256=plan_hash(plan),classification='supported');return plan
                second=semantic('adjudicate_semantics',first)
                attempt['adjudication']=second.model_dump()
                if all(a.verdict=='supported' for a in second.assessments):
                    self.report.update(status='validated',plan_sha256=plan_hash(plan),classification='reviewer_false_rejection');return plan
                if any(a.verdict=='ambiguous' for a in second.assessments) or [a.verdict for a in first.assessments]!=[a.verdict for a in second.assessments]:
                    self.report.update(status='manual_review_required',classification='requirement_ambiguity');raise ManualReview()
                kind='requirement_contradiction' if any(a.verdict=='contradiction' for a in second.assessments) else 'invalid_test'
                attempt['technical_kind']=kind
            if revision or adapter.calls>=adapter.settings.max_calls-2:
                self.report.update(status='manual_review_required',classification=kind);raise ManualReview(kind)
            self.report['repairs']+=1
            old=plan
            def valid(new):
                if not isinstance(new,Plan):new=Plan(requirements=old.requirements,scenarios=[s.model_dump() for s in new.scenarios])
                TestPlanner.validate(new,require_all=True,check_syntax=False)
                if new.requirements!=old.requirements or any(s.framework!=old.scenarios[0].framework for s in new.scenarios):raise ValueError('Plan changed requirements or runner')
                return new
            plan=adapter.generate('repair_tests',scenario_schema(old.requirements,old.scenarios[0].framework),
                'Repair this NEW not-yet-executed suite once. Preserve requirements exactly. Correct only the supplied technical/semantic error. '
                'Expected values come solely from the documents. No product execution results or oracle exist here. Never skip or weaken a documented check.',
                {'operation':'repair_tests','schema_style':'scenarios_only','requirements':docs,'files':[{'path':n,'content':t} for n,t in files],
                 'previous_plan':old.model_dump(),'validation_issue':attempt},valid)
        raise ManualReview()
