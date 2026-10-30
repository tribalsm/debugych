import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createGateway} from '../../scripts/serve-server-web.mjs';
const demo=JSON.parse(readFileSync(new URL('../../infra/server/public-demo.json',import.meta.url),'utf8'));
test('public catalog is bounded, legacy remains, every measured proof binds unchanged tests and verified candidate',()=>{
 assert.equal(demo.routes['/api/projects'].length,3);
 const server=createGateway({root:'.',origin:'https://debugych.test',upstream:'http://127.0.0.1:1',demo});server.close();
 for(const p of demo.routes['/api/projects'].slice(0,2)){
  const runs=demo.routes['/api/projects/'+p.id+'/runs'],initial=runs[0],proof=runs[1],verify=runs[2];
  assert.equal(initial.runtime,'runsc');assert.equal(proof.replay.source_sha256,initial.source_sha256);
  assert.equal(proof.replay.tests_sha256,initial.tests_sha256);
  assert.equal(verify.focused.source_sha256,verify.regression.source_sha256);
  assert.equal(initial.tests_sha256,verify.regression.tests_sha256);
  assert.equal(verify.regression.failed,0);assert.ok(verify.coverage.totals.percent_covered<100);assert.ok(verify.coverage.totals.num_branches>0);
  assert.equal(verify.baseline.image_id,verify.regression.image_id);
  assert.deepEqual(initial.cases.map(c=>c.test_id),verify.regression.cases.map(c=>c.test_id));
  assert.equal(demo.routes['/api/projects/'+p.id+'/fixes'][0].applied,false);
 }
 const duplicate=structuredClone(demo);duplicate.routes['/api/projects'].push(duplicate.routes['/api/projects'][0]);
 assert.throws(()=>createGateway({root:'.',origin:'https://debugych.test',upstream:'http://127.0.0.1:1',demo:duplicate}),/Invalid public demo/);
 const oversized=structuredClone(demo);oversized.routes['/api/projects']=Array.from({length:9},(_,i)=>({id:String(i)}));
 assert.throws(()=>createGateway({root:'.',origin:'https://debugych.test',upstream:'http://127.0.0.1:1',demo:oversized}),/Invalid public demo/);
});
test('historical live view has original AI tests, failed calls and no oracle, secrets or claims of new generation',()=>{
 const data=JSON.parse(readFileSync(new URL('../../apps/web/public/evidence/live-ai.json',import.meta.url),'utf8'));
 assert.equal(data.records.length,2);assert.ok(data.history_notice.includes('две Python'));
 for(const r of data.records){assert.equal(r.model,'gpt-6-luna');assert.equal(r.tests.length,4);assert.equal(r.original.runtime,'runsc');assert.equal(r.candidate.failed,0);assert.equal(r.candidate.errors,0);assert.equal(r.billed_usd,null);assert.equal(r.applied,false);assert.match(r.report_sha256,/^[a-f0-9]{64}$/);assert.equal(r.requests,r.calls.length)}
 assert.equal(data.records[0].failed_requests,1);
 assert.doesNotMatch(JSON.stringify(data),/LLM_API_KEY|Bearer |private.oracle|sk-[A-Za-z0-9_-]{16,}/);
});
