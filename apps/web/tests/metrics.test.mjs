import {test} from 'node:test';import assert from 'node:assert/strict';import {build} from 'esbuild';
await build({entryPoints:['src/testingMetrics.ts'],outdir:'node_modules/.cache/metrics-tests',bundle:true,platform:'node',format:'esm'});
const {testingMetrics}=await import('../node_modules/.cache/metrics-tests/testingMetrics.js');
const now=Date.parse('2026-10-30T00:00:00Z');
const run=(id,extra={})=>({id,operation:'run',status:'completed',created_at:'2026-10-29T12:00:00',passed:2,failed:0,errors:0,skipped:0,...extra});
test('case and attempt success have separate denominators; parent and verification are excluded',()=>{
 const rows=[run('1'),run('2',{passed:1,failed:1}),run('3',{status:'failed',passed:0}),run('4',{operation:'verify'}),run('5',{operation:'autonomous'}),run('6',{status:'running'}),run('1')];
 const m=testingMetrics(rows,30,now);assert.equal(m.attempts,3);assert.equal(m.successful,1);assert.equal(m.passRate,.75);assert.equal(m.successRate,1/3);assert.equal(m.infrastructure,1);assert.equal(m.pending,1);assert.equal(m.invalid,1);
});
test('empty, skipped, malformed and mismatched reports cannot become successful',()=>{
 assert.equal(testingMetrics([],30,now).successRate,null);
 for(const extra of [{passed:0,skipped:2},{passed:NaN},{passed:-1},{cases:[{status:'failed'}]},{passed:0}])assert.equal(testingMetrics([run('1',extra)],30,now).successful,0);
 const m=testingMetrics([run('1',{passed:0,skipped:2})],30,now);assert.equal(m.passRate,null);assert.equal(m.successRate,0);
});
test('legacy results derive absent summary fields from actual cases',()=>{
 const m=testingMetrics([run('legacy',{errors:undefined,skipped:undefined,cases:[{status:'passed'},{status:'passed'}]})],30,now);assert.equal(m.successful,1);assert.equal(m.passRate,1);
});
test('bounded UTC intervals reject missing/future dates and preserve distinct repeat attempts',()=>{
 const rows=[run('1',{created_at:'2026-09-01T00:00:00Z'}),run('2',{created_at:undefined}),run('3',{created_at:'2027-01-01T00:00:00Z'}),run('4'),run('5')];
 assert.equal(testingMetrics(rows,30,now).attempts,2);assert.equal(testingMetrics(rows,30,now).excluded,3);assert.equal(testingMetrics(rows,null,now).attempts,5);
});
