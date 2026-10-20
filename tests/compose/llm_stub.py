"""Explicit CONTRACT TEST provider. No inference, never used by default Compose."""
import json
import hashlib
from fastapi import FastAPI
app=FastAPI()

def legacy(body:dict):
    context=body['messages'][-1]['content']
    if 'FILE index.html' in context:
        payload={'requirements':[{'key':'R1','text':'Кнопка Добавить увеличивает счётчик на один; начальное значение 0; заголовок Счётчик.'}],
                 'scenarios':[{'title':'Браузерный счётчик · Playwright','requirement':'R1',
                   'gherkin':'Feature: Counter\nScenario: Increment\n Given counter starts at zero\n When Add is clicked\n Then counter equals one',
                   'code':'''import {test,expect} from '@playwright/test';
test('Заголовок', async ({page}) => {await page.goto('/'); await expect(page.getByRole('heading')).toHaveText('Счётчик');});
test('Начальное значение', async ({page}) => {await page.goto('/'); await expect(page.locator('#value')).toHaveText('0');});
test('Увеличение на один', async ({page}) => {await page.goto('/'); await page.getByRole('button',{name:'Добавить'}).click(); await expect(page.locator('#value')).toHaveText('1');});
''','framework':'playwright'}]}
        return {'choices':[{'message':{'content':json.dumps(payload)}}]}
    assert 'calc.py' in context and 'R1' in context
    if context.startswith('{'):
        value=json.loads(context)
        if value.get('operation')=='fix':
            source=next(f for f in value['files'] if f['path']=='calc.py')
            trap='REGRESSION_TRAP' in value['requirement'] and value['proposal_attempt']==1
            after='def add(a,b): return 5\n' if trap else source['content'].replace('return a-b','return a+b')
            payload={'explanation':'Тестовое предложение: намеренная регрессия' if trap else 'Сложение должно использовать оператор + вместо -.',
                     'changes':[{'path':source['path'],'before_sha256':hashlib.sha256(source['content'].encode()).hexdigest(),'content':after}]}
            return {'choices':[{'message':{'content':json.dumps(payload)}}]}
    payload={'requirements':[{'key':'R1','text':'Функция add возвращает сумму двух чисел.'+(' REGRESSION_TRAP' if 'REGRESSION_TRAP' in context else '')}],
             'scenarios':[{'title':'Сложение двух положительных чисел','requirement':'R1',
                           'gherkin':'Feature: Addition\nScenario: Positive values\n Given two and three\n When add is called\n Then result is five',
                           'code':'from calc import add\n\ndef test_add():\n    assert add(2,3)==5\n', 'framework':'pytest'},
                          {'title':'Границы сложения','requirement':'R1','gherkin':'Feature: Addition\nScenario: Zero\n Given a zero operand\n When add is called\n Then the value is unchanged',
                           'code':'from calc import add\n\ndef test_zero_right(): assert add(5,0)==5\ndef test_zero_both(): assert add(0,0)==0\n','framework':'pytest'}]}
    return {'choices':[{'message':{'content':json.dumps(payload)}}]}


def reply(payload):
    return {'choices':[{'finish_reason':'stop','message':{'content':json.dumps(payload,ensure_ascii=False)}}]}

def scenario_reply(payload,value):
    return reply({'scenarios':payload['scenarios']} if value.get('schema_style')=='scenarios_only' else payload)

@app.post('/v1/chat/completions')
def complete(body:dict):
    context=body['messages'][-1]['content']
    value=json.loads(context)
    if value.get('operation') in ('validate_semantics','adjudicate_semantics'):
        docs={r['key']:r for r in value['requirements']}
        ambiguous=any('CONTRACT_AMBIGUOUS' in r['quote'] for r in docs.values())
        reject=value['operation']=='validate_semantics' and any('CONTRACT_FALSE_REVIEW' in r['quote'] for r in docs.values())
        result={'assessments':[{'scenario':s['index'],'verdict':'ambiguous' if ambiguous else 'invalid_test' if reject else 'supported','requirement_quote':docs[s['requirement']]['quote'],
            'assertion_indexes':list(range(len(s['assertions']))),'rationale':'Explicit contract fixture: documented synthetic assertion.'} for s in value['scenarios']]}
        if value['operation']=='adjudicate_semantics':
            result['counterarguments']=[] if ambiguous else [{'scenario':s['index'],'disputed_claim':'Explicit contract fixture: documented synthetic assertion.',
                'code_quote':s['code'],'requirement_quote':docs[s['requirement']]['quote'],'rationale':'Contract independent check refutes the intentionally wrong rejection using the unchanged assertion and quoted addition requirement.'} for s in value['scenarios']]
        return reply(result)
    if value.get('operation')=='repair_tests':
        result=value['previous_plan']
        result['scenarios'][0]['code']='from calc import add\ndef test_add(): assert add(2,3)==5'
        return scenario_reply(result,value)
    if value.get('operation')=='review_tests':
        # Explicit negative fixture for the draft review end-to-end test.
        return reply({'approved':False,'issues':['CONTRACT reviewer intentionally rejects this valid draft to exercise explicit review.']})
    if value.get('operation')=='extract_requirements':
        documents=value['documents'];text='\n'.join(d['content'] for d in documents)
        if 'CONTRACT_BAD_SCHEMA' in text:return reply({'requirements':[]})
        novel='Dispatch Quotes' in text or 'Seat Desk' in text
        if novel:
            import re
            requirements=[]
            for d in documents:
                for line in d['content'].splitlines():
                    match=re.match(r'(R\d+)\. (.+)',line)
                    if match:requirements.append({'key':match[1],'text':match[2],'source':d['path'],'quote':line})
        else:
            counter='счётчик' in text.lower()
            legacy_context=('FILE index.html\n' if counter else 'FILE calc.py\n')+text+' R1'
            plan=json.loads(legacy({'messages':[{'content':legacy_context}]})['choices'][0]['message']['content'])
            d=documents[0]
            requirements=[{**r,'source':d['path'],'quote':d['content'].splitlines()[-1]} for r in plan['requirements']]
        payload={'requirements':requirements}
        if '"acceptance_contract"' in body['messages'][0]['content']:
            payload['acceptance_contract']={'cases':[{'requirement':r['key'],'action':'Exercise the documented input.','expected':r['text']} for r in requirements]}
        return reply(payload)
    if value.get('operation')=='generate_tests':
        paths={f['path'] for f in value['files']}
        if value.get('planner_version')==2 and ('dispatch_api.py' in paths or 'SeatDesk.tsx' in paths):
            from planner_fixtures import plan
            return reply(plan(value))
        if 'dispatch_api.py' in paths:
            code="""from fastapi.testclient import TestClient
from dispatch_api import app
client=TestClient(app)
def test_weight_boundary(): assert client.get('/quote',params={'weight':1000}).json()['price']==700
def test_small_parcel(): assert client.get('/quote',params={'weight':500}).json()['price']==700
def test_invalid_weight(): assert client.get('/quote',params={'weight':0}).status_code==422
"""
            title='Dispatch: вес и границы';framework='pytest'
        elif 'SeatDesk.tsx' in paths:
            code="""import {test,expect} from '@playwright/test';
test('Все места доступны для бронирования',async({page})=>{await page.goto('/');await page.getByLabel('Количество').fill('6');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('0');});
test('Часть мест',async({page})=>{await page.goto('/');await page.getByLabel('Количество').fill('2');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('4');});
test('Нулевое количество',async({page})=>{await page.goto('/');await page.getByLabel('Количество').fill('0');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.locator('p[role="status"]')).toHaveText('Введите количество от 1 до остатка');});
"""
            title='Seat Desk: бронирование';framework='playwright'
        else:
            legacy_context='\n'.join('FILE '+f['path']+'\n'+f['content'] for f in value['files'])+json.dumps(value['requirements'])
            payload=json.loads(legacy({'messages':[{'content':legacy_context}]})['choices'][0]['message']['content'])
            if 'CONTRACT_BROKEN_TEST' in legacy_context:payload['scenarios'][0]['code']='def broken('
            payload['requirements']=value['requirements'];return scenario_reply(payload,value)
        lines=code.strip().splitlines()
        header='\n'.join(lines[:3] if framework=='pytest' else lines[:1])+'\n'
        cases=lines[3:] if framework=='pytest' else lines[1:]
        scenarios=[]
        for i,line in enumerate(cases):
            scenarios.append({'title':title if i==0 else title+' · контроль '+str(i),
                              'requirement':'R2' if i==2 else 'R1',
                              'gherkin':'Feature: Documented behavior\nScenario: '+('Boundary' if i==0 else 'Positive control' if i==1 else 'Invalid input')+'\n Given a valid initial state\n When input is submitted\n Then the documented result is returned',
                              'code':header+line+'\n','framework':framework})
        return scenario_reply({'requirements':value['requirements'],'scenarios':scenarios},value)
    if value.get('operation')=='fix':
        if any('CONTRACT_WRONG_PATCH' in f['content'] for f in value['files']):
            return reply({'explanation':'Intentional contract rejection probe','changes':[{'path':'tests/test_changed.py','before_sha256':'0'*64,'content':'def test_cheat(): assert True'}]})
        paths={f['path'] for f in value['files']}
        name='dispatch_api.py' if 'dispatch_api.py' in paths else 'SeatDesk.tsx' if 'SeatDesk.tsx' in paths else None
        if name:
            source=next(f for f in value['files'] if f['path']==name)
            before,after=('weight<1000','weight<=1000') if name.endswith('.py') else ('amount<available','amount<=available')
            return reply({'explanation':'Подготовленный контрактный кандидат: включительная граница по R1.','changes':[{'path':name,'before_sha256':source['sha256'],'content':source['content'].replace(before,after).replace('weight<200','weight<=200').replace("function reset(){setAvailable(6);setMessage('');}","function reset(){setAvailable(6);setQuantity('1');setMessage('');}")}]})
        if 'calc.py' in paths:return legacy({'messages':[{'content':json.dumps(value)}]})
    raise ValueError('Unknown explicit contract fixture')
