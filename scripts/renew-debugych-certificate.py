"""Renew only the new Debugych certificate over IPv4, retaining normal TLS checks."""
import argparse
import runpy
import socket
import sys

def renew(dry_run=False):
    import urllib3.util.connection
    previous_family=urllib3.util.connection.allowed_gai_family
    previous_args=sys.argv
    # This host's IPv6 ACME transport fails. Do not change host networking,
    # other certificates, certificate verification, or any VPN configuration.
    urllib3.util.connection.allowed_gai_family=lambda:socket.AF_INET
    sys.argv=['certbot','renew','--cert-name','debugych-sslip-20261030','--non-interactive','--no-random-sleep-on-renew']
    if dry_run:sys.argv+=['--dry-run','--run-deploy-hooks']
    try:return runpy.run_path('/usr/bin/certbot',run_name='__main__')
    finally:
        urllib3.util.connection.allowed_gai_family=previous_family
        sys.argv=previous_args

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run',action='store_true')
    renew(parser.parse_args().dry_run)
