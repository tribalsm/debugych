"""Validate deployment settings without printing secrets or running provider calls."""
import sys
from pathlib import Path
from urllib.parse import urlsplit

def validate(path):
    values = {}
    for line in Path(path).read_text().splitlines():
        if line.strip() and not line.lstrip().startswith('#'):
            key, value = line.split('=', 1)
            values[key.strip()] = value.strip()
    if len(values.get('POSTGRES_PASSWORD','')) < 32 or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in values['POSTGRES_PASSWORD']):
        raise ValueError('A new URL-safe database password of at least 32 characters is required')
    if values.get('LLM_MODEL') != 'gpt-6-luna' or values.get('LLM_BASE_URL','').rstrip('/') != 'https://triklz27.ru/v1':
        raise ValueError('Use the approved provider and model; changes need owner approval')
    for name, ceiling in [('LLM_MAX_CALLS',4),('LLM_MAX_DAILY_CALLS',6),('LLM_MAX_JOB_USD',1),('LLM_MAX_DAILY_USD',1)]:
        if not 0 < float(values.get(name,'0')) <= ceiling:
            raise ValueError('Budget/retry policy exceeds the release ceiling or is missing')
    print('Configuration valid. No keys printed; provider not called.')

if __name__ == '__main__':
    validate(sys.argv[1])
