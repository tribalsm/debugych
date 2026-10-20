from fastapi import FastAPI
from pydantic import BaseModel,Field

app=FastAPI()
class Estimate(BaseModel):
    units: int = Field(strict=True,ge=1,le=9)
    unit_cents: int = Field(strict=True,ge=1,le=10000)
    member: bool = False

@app.post('/estimate')
def estimate(item: Estimate):
    subtotal=item.units*item.unit_cents
    discounted=round(subtotal*0.8) if item.member else subtotal
    delivery=60 if subtotal<500 else 0
    return {'subtotal':subtotal,'discounted':discounted,'delivery':delivery,'total':discounted+delivery}
