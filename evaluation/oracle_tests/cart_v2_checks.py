from fastapi.testclient import TestClient
from cart_api import app
client=TestClient(app)
def test_monthly():
    assert client.post('/estimate',json={'units':2,'unit_cents':250}).json()=={'subtotal':500,'discounted':500,'delivery':0,'total':500}
def test_floor():
    assert client.post('/estimate',json={'units':1,'unit_cents':101,'member':True}).json()=={'subtotal':101,'discounted':80,'delivery':60,'total':140}
def test_discounted_shipping():
    assert client.post('/estimate',json={'units':3,'unit_cents':180,'member':True}).json()=={'subtotal':540,'discounted':432,'delivery':60,'total':492}
def test_reject():
    assert client.post('/estimate',json={'units':'2','unit_cents':250}).status_code==422
