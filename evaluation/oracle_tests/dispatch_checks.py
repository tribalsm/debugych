from fastapi.testclient import TestClient
from dispatch_api import app
client=TestClient(app)

def test_weight_tier():assert client.get('/quote',params={'weight':1000}).json()['price']==700
def test_pickup_boundary():assert client.get('/quote',params={'weight':200,'pickup':True}).json()['price']==0
def test_small_quote():assert client.get('/quote',params={'weight':500}).json()['price']==700
def test_invalid_weight():assert client.get('/quote',params={'weight':0}).status_code==422
