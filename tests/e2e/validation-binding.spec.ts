import {test,expect} from '../../apps/web/node_modules/@playwright/test';
import {validationMatches} from '../../apps/web/src/validationBinding';
import {agentState} from '../../apps/web/src/MascotSlot';

test('Редактирование кода или требований не сохраняет статус Validated по старому ID',()=>{
 const testCase={id:'test',title:'Example',requirement:'R1',gherkin:'Feature: x',code:'assert add(2,3)==5',framework:'pytest',dimensions:['positive'],validation_id:'job',validation_plan_sha256:'hash',scenario_index:0};
 const requirements=[{key:'R1',text:'Return a sum'}];
 const jobs=[{id:'job',validation:{status:'validated',plan_sha256:'hash',attempts:[{plan_sha256:'hash',draft:{requirements,scenarios:[testCase]}}]}}];
 expect(validationMatches(testCase,requirements,jobs)).toBe(true);
 expect(validationMatches({...testCase,code:'assert True'},requirements,jobs)).toBe(false);
 expect(validationMatches(testCase,[{key:'R1',text:'Return a product'}],jobs)).toBe(false);
 expect(validationMatches({...testCase,validation_id:'other'},requirements,jobs)).toBe(false);
});

test('Агент не объявляет успех по прошедшему тесту или неподтверждённому отклонению',()=>{
 expect(agentState([{status:'completed',operation:'run'}],[{status:'reproduced'}])).toBe('idle');
 expect(agentState([{status:'failed',operation:'run'}],[])).toBe('error');
 expect(agentState([{status:'running',operation:'autonomous',stage:'fix_verification'}],[])).toBe('fixing');
 expect(agentState([{status:'manual_review_required',operation:'autonomous'}],[])).toBe('idle');
 expect(agentState([{status:'completed',operation:'verify',verified:true}],[{status:'fix_verified'}])).toBe('success');
});
