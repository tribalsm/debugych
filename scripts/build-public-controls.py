"""Generate saved observations for authored controls using the existing gVisor runner.
Run inside the trusted supervisor. No AI, API credentials, user projects or patch apply.
"""
import hashlib
import json
from uuid import uuid4
from services.runner.contracts import SandboxJob
from services.runner.supervisor import execute_snapshot

PYTHON = '''def shipping(total, member=False):
    if total < 0:
        raise ValueError("Negative amount")
    if member:
        return 30
    if total > 500:
        return 0
    return 60
'''
TYPESCRIPT = '''export function shipping(total: number, member = false): number {
  if (total < 0) {
    throw new Error('Negative amount');
  }
  if (member) return 30;
  if (total > 500) return 0;
  return 60;
}
'''
PYTEST = '''from shipping import shipping
def test_below_threshold(): assert shipping(499) == 60
def test_exact_threshold(): assert shipping(500) == 0
def test_above_threshold(): assert shipping(501) == 0
'''
PLAYWRIGHT = '''import {test,expect} from '@playwright/test';
test('Below threshold costs 60 cents',async({page})=>{
 await page.goto('/'); await page.getByLabel('Amount in cents').fill('499');
 await page.getByRole('button',{name:'Calculate'}).click();
 await expect(page.getByRole('status')).toHaveText('60');
});
test('Exactly 500 cents has free shipping',async({page})=>{
 await page.goto('/'); await page.getByLabel('Amount in cents').fill('500');
 await page.getByRole('button',{name:'Calculate'}).click();
 await expect(page.getByRole('status')).toHaveText('0');
});
'''
HTML = '<!doctype html><html lang="en"><meta charset="UTF-8"><title>Shipping control</title><label>Amount in cents<input type="number" value="499"></label><button>Calculate</button><output role="status"></output><script type="module" src="/main.ts"></script></html>'
MAIN = "import {shipping} from './rules';\ndocument.querySelector('button')!.onclick=()=>{document.querySelector('output')!.textContent=String(shipping(Number(document.querySelector('input')!.value)))};"


def main():
    output = []
    for language, profile, filename, source, code in [
        ('Python', None, 'shipping.py', PYTHON, PYTEST),
        ('TypeScript', 'playwright', 'rules.ts', TYPESCRIPT, PLAYWRIGHT),
    ]:
        test_id, requirement_id = uuid4(), uuid4()
        base = [{'path': filename, 'content': source}]
        if profile:
            base += [{'path': 'index.html', 'content': HTML}, {'path': 'main.ts', 'content': MAIN}]
        observations, image = {}, None
        for phase in ('original', 'proof', 'focused', 'regression'):
            fixed = phase in ('focused', 'regression')
            files = [{**f, 'content': f['content'].replace('total > 500', 'total >= 500') if f['path'] == filename and fixed else f['content']} for f in base]
            job = SandboxJob(id=uuid4(), profile=profile, files=files,
                             tests=[{'id': test_id, 'requirement_id': requirement_id, 'code': code}],
                             expected_image_id=image)
            result = execute_snapshot(job)
            assert result['runtime'] == 'runsc' and result['status'] == 'completed', result.get('error')
            assert result['errors'] == 0 and result['failed'] == (0 if fixed else 1), phase
            assert 0 < result['coverage']['totals']['percent_covered'] < 100, result['coverage']
            assert result['coverage']['totals']['num_branches'] > 0
            image = result['image_id']
            # No binary payloads or private machine paths are published.
            result['artifacts'] = []
            observations[phase] = {'id': str(job.id), **result}
        output.append({'language': language, 'framework': 'playwright' if profile else 'pytest',
                       'source': base, 'test_id': str(test_id), 'requirement_id': str(requirement_id),
                       'code': code, 'test_sha256': hashlib.sha256(code.encode()).hexdigest(),
                       'observations': observations})
    print('PUBLIC_CONTROLS_JSON=' + json.dumps(output))


if __name__ == '__main__':
    main()
