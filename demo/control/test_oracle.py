"""Independent acceptance oracle; excluded from generated-plan context."""
import importlib.util
from pathlib import Path
import pytest

@pytest.fixture
def shop():
    path = Path(__file__).resolve().parents[1] / 'sample-python-app/shop.py'
    spec = importlib.util.spec_from_file_location('oracle_shop', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def test_inclusive_balance_oracle(shop):
    # Deliberately fails for the supplied buggy version.
    assert [shop.pay(b, 100) for b in (99, 100, 101)] == [False, True, True]

def test_discount_and_order_oracle(shop):
    assert shop.discount(1000) == 900
    for quantity in (1, 100):
        assert shop.order(quantity) == quantity
