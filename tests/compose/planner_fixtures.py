"""Prepared contract answers. These fixtures NEVER constitute LLM discovery."""
def plan(context):
    python=any(f['path']=='dispatch_api.py' for f in context['files'])
    scenarios=[]
    def add(title,req,dimensions,code):
        scenarios.append({'title':title,'requirement':req,'dimensions':dimensions,
            'gherkin':f'Feature: Documented {req}\nScenario: {title}\n Given the documented initial state\n When the specified operation is performed\n Then all documented postconditions hold',
            'framework':'pytest' if python else 'playwright','code':code})
    if python:
        header="from fastapi.testclient import TestClient\nfrom dispatch_api import app\nimport pytest\nclient=TestClient(app)\n"
        add('Dispatch: вес и границы','R1',['positive','boundary'],header+"""
@pytest.mark.parametrize('weight,price',[(1,700),(999,700),(1000,700),(1001,1100),(5000,1100)])
def test_tiers(weight,price):
    response=client.get('/quote',params={'weight':weight})
    assert response.status_code==200
    assert response.json()=={'price':price,'currency':'RUB'}
""")
        add('Dispatch: неверный вес','R2',['negative','invalid_input','boundary'],header+"""
@pytest.mark.parametrize('weight',[0,-1,5001])
def test_rejected(weight): assert client.get('/quote',params={'weight':weight}).status_code==422
""")
        add('Dispatch: надбавка','R3',['positive','combination'],header+"""
@pytest.mark.parametrize('weight,price',[(500,1000),(1001,1400)])
def test_priority(weight,price): assert client.get('/quote',params={'weight':weight,'priority':True}).json()['price']==price
""")
        add('Dispatch: pickup и порядок правил','R4',['boundary','combination','invariant'],header+"""
@pytest.mark.parametrize('weight,priority,price',[(199,False,0),(200,False,0),(201,False,700),(200,True,300),(201,True,1000)])
def test_pickup(weight,priority,price):
    assert client.get('/quote',params={'weight':weight,'pickup':True,'priority':priority}).json()['price']==price
""")
    else:
        header="import {test,expect} from '@playwright/test';\n"
        add('Seat Desk: бронирование','R1',['positive','boundary','state'],header+"""
test('Весь остаток',async({page})=>{await page.goto('/');await expect(page.getByTestId('available')).toHaveText('6');await page.getByLabel('Количество').fill('6');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('0');await expect(page.locator('p[role="status"]')).toHaveText('Готово');});
""")
        add('Seat Desk: последовательные бронирования','R1',['state','invariant','boundary'],header+"""
test('Часть и нижняя граница',async({page})=>{await page.goto('/');await page.getByLabel('Количество').fill('2');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('4');await page.getByLabel('Количество').fill('1');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('3');});
""")
        add('Seat Desk: отклонение ввода сохраняет остаток','R2',['negative','invalid_input','invariant'],header+"""
test('Недопустимые количества',async({page})=>{await page.goto('/');for(const value of ['0','-1','1.5','7']){await page.getByLabel('Количество').fill(value);await page.getByRole('button',{name:'Забронировать',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('6');await expect(page.locator('p[role="status"]')).toHaveText('Введите количество от 1 до остатка');}});
""")
        add('Seat Desk: сброс всех полей','R3',['state','invariant'],header+"""
test('Полное восстановление состояния',async({page})=>{await page.goto('/');await page.getByLabel('Количество').fill('2');await page.getByRole('button',{name:'Забронировать',exact:true}).click();await page.getByRole('button',{name:'Сбросить',exact:true}).click();await expect(page.getByTestId('available')).toHaveText('6');await expect(page.getByLabel('Количество')).toHaveValue('1');await expect(page.locator('p[role="status"]')).toBeEmpty();await page.getByRole('button',{name:'Сбросить',exact:true}).click();await expect(page.getByLabel('Количество')).toHaveValue('1');});
""")
    return {'requirements':context['requirements'],'scenarios':scenarios}
