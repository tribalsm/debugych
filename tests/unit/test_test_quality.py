from copy import deepcopy
import pytest
from services.ai.engine import Plan, TestPlanner
from services.ai.quality import evaluate, compare_variant


def plan():
    return Plan(requirements=[{'key':'R1','text':'Reset restores quantity 1.'},{'key':'R2','text':'Zero is rejected.'}],scenarios=[
        {'title':'Reset','requirement':'R1','gherkin':'Feature: Reset\nScenario: Reset','code':'def test_reset(): assert True','framework':'pytest','dimensions':['state']}])


def observation(status='passed'):
    return {'status':'completed','runtime':'runsc','image_id':'pinned',
            'cases':[{'test_id':'t','name':'one','classname':'module','status':status,'traceback':'AssertionError' if status=='failed' else ''}],
            'coverage':{'totals':{'covered_lines':4,'num_statements':10,'covered_branches':1,'num_branches':4}},'coverage_kind':'measured'}


TESTS=[{'id':'t','requirement_id':'r1','dimensions':['negative']}]


def test_planner_rejects_previously_silent_requirement_omission():
    with pytest.raises(ValueError,match='требованию'):TestPlanner.validate(plan(),require_all=True)


def test_planner_accepts_all_grounded_links_and_retains_legacy():
    value=plan();TestPlanner.validate(value)
    second=value.scenarios[0].model_copy(update={'requirement':'R2','dimensions':['negative']})
    value.scenarios.append(second)
    assert TestPlanner.validate(value,require_all=True) is value


@pytest.mark.parametrize('gherkin',['Feature: Prices\nScenario Outline: Boundary\n Given weight <w>\n Then price is <p>\n Examples:\n |w|p|\n |1|700|',
                                  '# language: ru\nФункционал: Бронь\nСценарий: Сброс\n Дано изменённое состояние'])
def test_standard_outline_and_russian_dialect_are_not_rejected(gherkin):
    value=plan();value.scenarios[0].gherkin=gherkin
    assert TestPlanner.validate(value) is value


def test_dimension_enum_rejects_invented_category():
    with pytest.raises(ValueError):Plan.model_validate({**plan().model_dump(),'scenarios':[{**plan().scenarios[0].model_dump(),'dimensions':['secret']} ]})


def test_checklist_is_conditional_and_not_fixture_specific():
    assert 'Only if' in TestPlanner.CHECKLIST['authorization']
    assert 'document' in TestPlanner.CHECKLIST['exception']
    assert not any(x in str(TestPlanner.CHECKLIST) for x in ['pickup','SeatDesk','dispatch_api'])


def test_measured_quality_does_not_claim_full_requirement_coverage():
    result=evaluate(['r1','r2'],TESTS,observation('failed'))
    assert result['requirements']['exercise_ratio']==.5
    assert result['requirements']['with_passing_assertions']==[]
    assert result['requirements']['unexercised']==['r2']
    assert result['line_coverage']['ratio']==.4 and result['branch_coverage']['ratio']==.25
    assert result['negative_requirements_claimed_and_executed']==['r1']
    assert result['mutation']['score'] is None and 'score' not in result


@pytest.mark.parametrize('status',['error','skipped'])
def test_non_assertion_cases_do_not_exercise_requirements(status):
    result=evaluate(['r1'],TESTS,observation(status))
    assert result['requirements']['exercised']==[] and result['executable_module_ratio']==0


def test_infrastructure_failure_and_missing_module_are_not_quality():
    run=observation('failed');run['cases'][0]['traceback']='TimeoutError'
    result=evaluate(['r1'],TESTS+[{'id':'missing','requirement_id':'r1'}],run)
    assert result['infrastructure_cases']==1 and result['executable_module_ratio']==0


def test_one_passing_case_cannot_hide_broken_case_in_same_module():
    run=observation()
    run['cases'].append({**run['cases'][0],'name':'broken','status':'error','traceback':'ImportError'})
    result=evaluate(['r1'],TESTS,run)
    assert result['executable_module_ratio']==0 and result['partially_executable_modules']==1
    assert result['requirements']['exercised']==['r1']


@pytest.mark.parametrize('change',[{'status':'failed'},{'runtime':'runc'},{'cases':[],'coverage':None}])
def test_missing_measurements_are_not_100_percent(change):
    run={**observation(),**change}
    if run.get('coverage'):run['coverage']['totals']['num_branches']=0
    result=evaluate(['r1'],TESTS,run)
    assert result['branch_coverage']['ratio'] is None


def test_duplicate_or_foreign_case_cannot_inflate_quality():
    run=observation();run['cases']*=2
    assert evaluate(['r1'],TESTS,run)['observation_valid'] is False
    run=observation();run['cases'][0]['test_id']='foreign'
    assert evaluate(['r1'],TESTS,run)['observation_valid'] is False


def test_differential_detection_requires_good_reference():
    assert compare_variant(observation(),observation('failed'))['detected']
    assert not compare_variant(observation('failed'),observation('failed'))['eligible']
    assert not compare_variant(observation(),observation())['detected']


@pytest.mark.parametrize('change',[{'image_id':'other'},{'status':'failed'},{'runtime':'runc'}])
def test_mutation_infrastructure_is_excluded(change):
    assert not compare_variant(observation(),{**observation('failed'),**change})['eligible']


def test_mutation_missing_skipped_or_invalid_cases_are_excluded():
    for status in ['skipped','error']:
        assert not compare_variant(observation(),observation(status))['eligible']
    changed=deepcopy(observation('failed'));changed['cases'][0]['name']='different'
    assert not compare_variant(observation(),changed)['eligible']
    assert not compare_variant({**observation(),'tests_sha256':'original'},
                               {**observation('failed'),'tests_sha256':'edited'})['eligible']
