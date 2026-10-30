import importlib.util
import socket
import sys
from pathlib import Path
import pytest
from types import ModuleType

@pytest.fixture
def transport(monkeypatch):
    root=ModuleType('urllib3');util=ModuleType('urllib3.util');connection=ModuleType('urllib3.util.connection')
    connection.allowed_gai_family=lambda:socket.AF_UNSPEC
    root.util=util;util.connection=connection
    for name,value in [('urllib3',root),('urllib3.util',util),('urllib3.util.connection',connection)]:monkeypatch.setitem(sys.modules,name,value)
    return connection

spec=importlib.util.spec_from_file_location('certificate_renewal',Path('scripts/renew-debugych-certificate.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)

@pytest.mark.parametrize('dry_run',[False,True])
def test_certificate_renewal_is_scoped_and_keeps_tls_verification(monkeypatch,dry_run,transport):
    previous_args=sys.argv;previous_family=transport.allowed_gai_family;calls=[]
    def run(path,run_name):
        assert path=='/usr/bin/certbot' and run_name=='__main__'
        assert transport.allowed_gai_family()==socket.AF_INET
        calls.append(list(sys.argv))
    monkeypatch.setattr(module.runpy,'run_path',run)
    module.renew(dry_run)
    args=calls[0]
    assert args[args.index('--cert-name')+1]=='debugych-sslip-20261030'
    assert '--no-verify-ssl' not in args and '--force-renewal' not in args
    assert ('--dry-run' in args)==dry_run and ('--run-deploy-hooks' in args)==dry_run
    assert sys.argv is previous_args and transport.allowed_gai_family is previous_family

def test_certificate_failure_restores_process_state(monkeypatch,transport):
    previous_args=sys.argv;previous_family=transport.allowed_gai_family
    def fail(*args,**kwargs):raise RuntimeError('CA unavailable')
    monkeypatch.setattr(module.runpy,'run_path',fail)
    with pytest.raises(RuntimeError):module.renew()
    assert sys.argv is previous_args and transport.allowed_gai_family is previous_family
