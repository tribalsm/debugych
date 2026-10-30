"""Bounded OpenAI-compatible structured generation; no code execution."""
import os
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, create_model

class Requirement(BaseModel):
    model_config=ConfigDict(extra="forbid")
    key: str = Field(max_length=40)
    text: str = Field(min_length=1, max_length=4000)

class Scenario(BaseModel):
    model_config=ConfigDict(extra="forbid")
    title: str = Field(max_length=200)
    requirement: str
    gherkin: str = Field(max_length=8000)
    code: str = Field(max_length=16000)
    framework: str = Field(pattern='^(pytest|playwright)$')
    dimensions: list[Literal['positive','boundary','invalid_input','exception','state','invariant','combination','negative','authorization']] = Field(default_factory=lambda:['positive'],min_length=1,max_length=9)

class Plan(BaseModel):
    model_config=ConfigDict(extra="forbid")
    requirements: list[Requirement] = Field(min_length=1, max_length=40)
    scenarios: list[Scenario] = Field(min_length=1, max_length=40)

def scenario_schema(requirements,framework):
    """Only generate scenarios; requirement identity is server-owned, not echoed."""
    bound=create_model('BoundScenario',__base__=Scenario,
        requirement=(Literal[tuple(r.key for r in requirements)],...),framework=(Literal[framework],...))
    return create_model('GeneratedScenarios',__config__=ConfigDict(extra='forbid'),
        scenarios=(list[bound],Field(min_length=1,max_length=40)))

class TestReview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    approved: bool
    issues: list[str] = Field(max_length=12)

class AcceptanceCase(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requirement: str = Field(min_length=1,max_length=40,description='Exactly one existing requirement key, never requirement text or combined keys.')
    action: str = Field(min_length=1,max_length=600)
    expected: str = Field(min_length=1,max_length=600)

class AcceptanceContract(BaseModel):
    model_config=ConfigDict(extra='forbid')
    cases: list[AcceptanceCase] = Field(min_length=1,max_length=24)

class RequirementAnalyzer:
    @staticmethod
    def context(files):
        from services.ai.privacy import sanitize_files
        from services.ai.adapter import AIError
        files,_=sanitize_files(files)
        content='\n'.join(f'FILE {name}\n{text}' for name,text in files)
        if len(content)>int(os.getenv('LLM_CONTEXT_CHARS','40000')):raise AIError('context_limit_no_truncation')
        return content

class CodeAnalyzer:
    @staticmethod
    def summarize(files):
        import ast
        result = []
        for name, text in files:
            if name.endswith('.py'):
                try:
                    tree = ast.parse(text)
                    result.append({'file': name, 'functions': [{'name': n.name, 'line': n.lineno} for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]})
                except SyntaxError as error:
                    result.append({'file': name, 'error': str(error)})
            elif name.endswith(('.java', '.js','.mjs','.cjs','.ts','.tsx','.jsx','.html','.css')):
                result.append({'file': name, 'analysis': 'text-only', 'lines': len(text.splitlines())})
        return result

class TestPlanner:
    # A review checklist, not additional product requirements. Inapplicable checks
    # must not produce invented behavior (especially authorization and exceptions).
    CHECKLIST = {
        'boundary':'For every documented interval test endpoints and adjacent values, including inclusive endpoints.',
        'invalid_input':'Check documented input types/formats and rejected values; do not invent an error response.',
        'exception':'Exercise exceptions only where the document specifies failure behavior.',
        'state':'For state transitions/reset verify ALL documented state fields before and after; repeat an operation.',
        'invariant':'Assert documented invariants across a sequence, not only the success message.',
        'combination':'Combine interacting parameters/rules, especially ordering of discounts, surcharges and limits.',
        'negative':'Verify documented rejection AND unchanged state; distinguish infrastructure failures.',
        'authorization':'Only if authorization is specified, check permitted/denied identities and roles.'}

    @staticmethod
    def validate(plan, require_all=False, check_syntax=True):
        import ast
        import re
        keys = {r.key for r in plan.requirements}
        if len(keys) != len(plan.requirements) or any(s.requirement not in keys for s in plan.scenarios):
            raise ValueError('Некорректные связи требований и сценариев')
        if require_all and keys != {s.requirement for s in plan.scenarios}:
            raise ValueError('Каждому извлечённому требованию нужен исполняемый сценарий')
        for scenario in plan.scenarios:
            feature=re.search(r'^\s*(?:Feature|Business Need|Ability|Функция|Функционал|Свойство):\s*\S',scenario.gherkin,re.M)
            example=re.search(r'^\s*(?:Scenario|Example|Scenario Outline|Scenario Template|Сценарий|Пример|Структура сценария|Шаблон сценария):\s*\S',scenario.gherkin,re.M)
            if not feature or not example:
                raise ValueError('Требуется Gherkin Feature и Scenario')
            if scenario.framework == 'pytest' and check_syntax:
                try:
                    ast.parse(scenario.code)
                except SyntaxError as error:
                    raise ValueError('Сгенерированный Python не проходит синтаксическую проверку') from error
        return plan

class ExtractedRequirement(Requirement):
    source: str = Field(min_length=1,max_length=200)
    quote: str = Field(min_length=1,max_length=2000)

class RequirementsDocument(BaseModel):
    model_config=ConfigDict(extra='forbid')
    requirements: list[ExtractedRequirement] = Field(min_length=1,max_length=40)

class BrowserRequirementsDocument(RequirementsDocument):
    acceptance_contract: AcceptanceContract

class TestGenerator:
    @staticmethod
    def generate(files,adapter=None,validator=None):
        from apps.api.ai_runtime import current
        from services.ai.privacy import sanitize_files
        from services.ai.adapter import AIError
        adapter=adapter or current()
        if not adapter.settings.key:raise AIError('missing_LLM_API_KEY')
        files,_=sanitize_files(files)
        documents={name:text for name,text in files if name.lower().endswith(('.md','.pdf','.docx'))}
        if not documents:raise AIError('requirements_document_required')
        source=[{'path':name,'content':text} for name,text in files if name not in documents]
        framework='pytest' if any(f['path'].endswith('.py') for f in source) else 'playwright'
        browser_contract=framework=='playwright' and adapter.settings.review_tests
        def grounded(value):
            keys=set()
            for requirement in value.requirements:
                if requirement.key in keys or requirement.source not in documents or requirement.quote not in documents[requirement.source]:
                    raise ValueError('Ungrounded requirement')
                keys.add(requirement.key)
            if browser_contract and {c.requirement for c in value.acceptance_contract.cases}!=keys:
                raise ValueError('Некорректные связи требований и сценариев')
            return value
        extracted=adapter.generate('extract_requirements',BrowserRequirementsDocument if browser_contract else RequirementsDocument,
            'Extract explicit requirements only from the supplied documents. Each requirement must cite its exact source path and a verbatim quote present in that document. Do not invent requirements. '
            +('Also derive a compact acceptance_contract ONLY from these documents, without implementation. Each case.requirement must be exactly one extracted key. Cover every extracted key. '
              'Give concrete actions/inputs and exact expected observable postconditions for each documented clause: interval endpoints, rejected inputs and ALL fields restored by reset. '
              'Describe independent cases with initial state; combine related input values compactly, prefer at most 12 cases. Do not invent undocumented behavior.' if browser_contract else ''),
            {'operation':'extract_requirements','documents':[{'path':name,'content':text} for name,text in documents.items()]},grounded)
        requirements=[Requirement(key=r.key,text=r.text) for r in extracted.requirements]
        adapter.requirement_evidence=[r.model_dump() for r in extracted.requirements]
        def valid_plan(plan):
            if validator and not isinstance(plan,Plan):plan=Plan(requirements=requirements,scenarios=[s.model_dump() for s in plan.scenarios])
            TestPlanner.validate(plan,require_all=True,check_syntax=validator is None)
            if [r.model_dump() for r in plan.requirements]!=[r.model_dump() for r in requirements] or any(t.framework!=framework for t in plan.scenarios):
                raise ValueError('Plan changed requirements or runner')
            return plan
        # Freeze expectations during document extraction, BEFORE source exposure.
        # Combining these two document-only tasks saves a paid round trip.
        contract=extracted.acceptance_contract if browser_contract else None
        adapter.acceptance_contract=contract.model_dump() if contract else None
        adapter.review_drafts=[]
        if getattr(adapter,'retrieve_source',None):source=adapter.retrieve_source(files,requirements)
        acceptance={'acceptance_contract':contract.model_dump()} if contract else {}
        plan=adapter.generate('generate_tests',scenario_schema(requirements,framework) if validator else Plan,
            'Study code structure and apply every relevant item of planning_checklist. Source entries marked partial are retrieved fragments with original line ranges, not complete files. Never infer absent behavior or requirements from missing context. Every supplied requirement MUST have at least one executable scenario linked by key. '
            'Tag each scenario dimensions with applicable checks; tags are planning claims, not proof of quality. Test each documented clause, not just one example per requirement. '
            'Keep the initial suite compact: use parameterization instead of redundant code, usually one or two modules per requirement. '
            'Consider boundary values, invalid types/formats, specified exceptions, states, business invariants, parameter combinations, negatives and documented authorization. '
            'Never invent requirements or undocumented error contracts. Use parameterized cases where useful, with independent assertions for each clause. '
            'Generate Gherkin scenarios with executable assertions. '
            +('Return ONLY scenarios; requirements are read-only references, do not echo them. Use each supplied requirement key exactly as defined by its enum. ' if validator else 'Echo the supplied requirements unchanged and in the same order. ')+
            'Each scenario.gherkin must be self-contained: include its own English Feature: heading and Scenario: or Scenario Outline: heading, then Given/When/Then steps. Never return only steps or a scenario fragment without Feature. '
            'For Python use pytest; fixed environment includes FastAPI and httpx. For ASGI apps import app from the submitted module and use FastAPI TestClient. '
            'For JS/TS use playwright: import {test,expect} from "@playwright/test" and page.goto("/"); baseURL is http://127.0.0.1:4173. '
            'The sandbox builds root index.html and local JS/TS/TSX modules with esbuild. React 19 is installed. No npm/pip install, external servers, dependencies, network, config or commands. '
            'Use precise accessible selectors: output elements can also have implicit status role; disambiguate message elements. '
            'For parameterized JS tests, destructure array rows with [a,b], object rows with {a,b}; every test title must be unique and inputs must never be undefined. '
            'When acceptance_contract is provided, use its checks as a test design derived before source exposure. Documents remain authoritative; do not treat illustrative inputs or ordering as additional product requirements. '
            'For compact browser suites prefer explicit test() cases with literal unique titles and literal inputs over loops/destructuring. '
            'For a message use an explicit element selector qualified by its role, e.g. page.locator(\'p[role="status"]\') when that element exists; do not use a broad status role. '
            'For each documented postcondition derive the expected value from requirements independently of implementation. Implementations are potentially buggy; never copy their current state transitions into expected values. '
            'Tests must assert documented behavior, never current implementation just to make tests pass. Do not mark expected failures or skip cases. Java is analysis-only.',
            {'operation':'generate_tests',**({'schema_style':'scenarios_only'} if validator else {}),'planner_version':3 if contract else 2,**acceptance,'planning_checklist':TestPlanner.CHECKLIST,'requirements':[r.model_dump() for r in requirements],'files':source,'code_structure':CodeAnalyzer.summarize(files),'framework':framework},valid_plan)
        if validator:
            plan=validator(plan,files,extracted.requirements,adapter)
        elif adapter.settings.review_tests:
            def consistent_review(value):
                if value.approved != (not value.issues):raise ValueError('Inconsistent review')
                return value
            for revision in range(2):
                limit=adapter.settings.output_tokens
                try:
                    adapter.settings.output_tokens=min(limit,512)
                    review=adapter.generate('review_tests',TestReview,
                        'Review this NEW, not-yet-executed test suite against explicit documented requirements only. You are intentionally not given implementation or execution results. '
                        'Reject assertions that contradict any documented postcondition or preserve current behavior instead of a specified value. '
                        'Check parameterization/destructuring, unique names, undefined inputs and ambiguous role selectors (output can also be status). '
                        'Reject only concrete false expected values or unequivocal executable errors. Missing extra coverage is advisory, not a reason to reject a valid suite. '
                        'Do NOT demand exhaustive enumeration of an interval, a particular narrative sequence or literal example inputs from the acceptance contract. These are illustrative test designs, not additional requirements. '
                        'Trace setup actions arithmetically before judging preconditions: a valid operation reaching a different state counts as changing state. Equivalent ways of reaching a state are valid unless the document specifies a sequence. '
                        'DOM structure is intentionally withheld: a precise CSS selector is allowed even when the document does not specify DOM roles. Do not infer ambiguity merely from a qualified role selector. '
                        'Return concise issues grounded in requirement keys. Do not invent requirements. Approved requires no issues.',
                        {'operation':'review_tests',**acceptance,'requirements':[r.model_dump() for r in requirements],'scenarios':[s.model_dump() for s in plan.scenarios]},
                        consistent_review)
                finally:adapter.settings.output_tokens=limit
                # Project-owned draft evidence, never a log or executable suite.
                # Retained even if the bounded correction/deadline subsequently fails.
                adapter.review_drafts.append({'plan':plan.model_dump(),'review':review.model_dump()})
                if review.approved:break
                if revision==1:raise AIError('test_review_rejected')
                # Regenerate only before persistence/first execution. No runner
                # results or hidden oracle enter this correction loop.
                plan=adapter.generate('generate_tests',Plan,
                    'Correct the technical and requirement-alignment issues in this NEW plan before its first execution. Preserve supplied requirement text/order and framework. '
                    'Expected behavior comes only from documents, never from current implementation or a desire for passing tests. '
                    'Each Gherkin field needs Feature: and Scenario: or Scenario Outline:. Use unique test names and correct data destructuring. '
                    'Use exact selectors for message elements; output may also have implicit status role. Never skip or mark expected failures.',
                    {'operation':'generate_tests','planner_version':3 if contract else 2,**acceptance,'requirements':[r.model_dump() for r in requirements],
                     'framework':framework,'files':source,'previous_plan':plan.model_dump(),'review_issues':review.issues},valid_plan)
        # Evidence is recorded separately, never changes the executable test schema.
        adapter.requirement_evidence=[r.model_dump() for r in extracted.requirements]
        return plan


class FailureAnalyzer:
    @staticmethod
    def classify(case, linked_requirement=False, controlled=False):
        if case['status'] == 'error':
            return 'infrastructure'
        if case['status'] != 'failed':
            return 'none'
        trace = case.get('traceback') or ''
        if any(s in trace for s in ['ModuleNotFoundError', 'ImportError', 'TimeoutError', 'SyntaxError','strict mode violation','TargetClosedError','browserType.launch']):
            return 'infrastructure'
        if any(marker in trace for marker in ['AssertionError','Failed: DID NOT RAISE','Failed: DID NOT WARN','Error: expect(']):
            return 'confirmed' if linked_requirement and controlled else 'reproduced'
        return 'suspected'

class FixGenerator:
    @staticmethod
    def demo_patch(source):
        import difflib
        fixed = source.replace('return balance > amount', 'return balance >= amount')
        return {'file': 'shop.py', 'before': source, 'after': fixed, 'diff': ''.join(difflib.unified_diff(source.splitlines(True), fixed.splitlines(True), fromfile='a/shop.py', tofile='b/shop.py')), 'origin': 'prepared-demo', 'explanation': 'R1 допускает платёж при равенстве баланса и суммы. Исправляется оператор сравнения.'}

class VerificationEngine:
    @staticmethod
    def assess(original, candidate):
        original_failed = {c['name'] for c in original['cases'] if c['status'] == 'failed'}
        before_passed = {c['name'] for c in original['cases'] if c['status'] == 'passed'}
        after_passed = {c['name'] for c in candidate['cases'] if c['status'] == 'passed'}
        return {'original_fixed': bool(original_failed) and original_failed <= after_passed, 'regressions_absent': before_passed <= after_passed, 'full_correctness_proven': False}
