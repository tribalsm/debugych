import importlib.util
from pathlib import Path
import pytest

ROOT = Path(__file__).resolve().parents[2]

def independent_checks(shop):
    outcomes = []
    for check in [lambda: shop.pay(100,100) is True, lambda: shop.discount(1000)==900, lambda: shop.order(100)==100]:
        try:
            outcomes.append(check())
        except ValueError:
            outcomes.append(False)
    return outcomes

@pytest.mark.parametrize('variant,expected', [('correct',[True,True,True]),('discount-boundary',[True,False,True]),('quantity-boundary',[True,True,False])])
def test_independent_oracle_identifies_documented_defect(variant,expected):
    spec = importlib.util.spec_from_file_location('trusted_variant', ROOT / 'demo/versions' / variant / 'shop.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert independent_checks(module) == expected
