from fastapi import FastAPI, Query

app=FastAPI(title='Dispatch Quotes')

@app.get('/quote')
def quote(weight: int = Query(gt=0,le=5000),priority: bool=False,pickup: bool=False):
    price=700 if weight<1000 else 1100
    if pickup and weight<200:
        price=0
    if priority:
        price+=300
    return {'price':price,'currency':'RUB'}
