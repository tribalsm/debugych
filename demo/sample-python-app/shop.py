"""Trusted demonstration fixture. Never import uploaded user code here."""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title='Demo shop')

def pay(balance: int, amount: int) -> bool:
    if balance < 0 or amount <= 0:
        raise ValueError('Invalid payment')
    return balance > amount

def discount(total: int) -> float:
    if total < 0:
        raise ValueError('Invalid total')
    return total * (0.9 if total >= 1000 else 1)

def order(quantity: int) -> int:
    if quantity < 1 or quantity > 100:
        raise ValueError('Quantity must be 1..100')
    return quantity

class Payment(BaseModel):
    balance: int
    amount: int

@app.post('/pay')
def payment(value: Payment):
    try:
        return {'accepted': pay(value.balance, value.amount)}
    except ValueError as error:
        raise HTTPException(422, str(error)) from error
