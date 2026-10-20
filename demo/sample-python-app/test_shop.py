import pytest
from shop import pay, discount, order

def test_exact_balance():
    assert pay(1000, 1000) is True, 'R1: exact balance must be accepted'

def test_available_balance():
    assert pay(1001, 1000) is True

def test_insufficient_balance():
    assert pay(999, 1000) is False

@pytest.mark.parametrize('balance,amount', [(100, 0), (100, -1), (-1, 1)])
def test_invalid_payment(balance, amount):
    with pytest.raises(ValueError):
        pay(balance, amount)

@pytest.mark.parametrize('value,expected', [(999, 999), (1000, 900), (1001, 900.9)])
def test_discount(value, expected):
    assert discount(value) == pytest.approx(expected)

def test_negative_total():
    with pytest.raises(ValueError):
        discount(-1)

@pytest.mark.parametrize('quantity', [1, 100])
def test_order(quantity):
    assert order(quantity) == quantity

@pytest.mark.parametrize('quantity', [0, 101])
def test_invalid_order(quantity):
    with pytest.raises(ValueError):
        order(quantity)
