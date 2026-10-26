import {test} from 'node:test';import assert from 'node:assert/strict';import {build} from 'esbuild';
await build({entryPoints:['src/resultTarget.ts'],outdir:'node_modules/.cache/release-tests',bundle:true,platform:'node',format:'esm'});
const {targetError}=await import('../node_modules/.cache/release-tests/resultTarget.js');
test('a historical verification remains addressable only when bound to the same immutable patch',()=>{
 const t={section:'verification',bug:'b',fix:'f',run:'old'},bugs=[{id:'b'}],fixes=[{id:'f',bug_id:'b',verification_id:'new',patch_sha256:'hash'}];
 assert.equal(targetError(t,bugs,fixes,[{id:'old',fix_id:'f',patch_sha256:'hash'}]),undefined);
 assert.match(targetError(t,bugs,fixes,[{id:'old',fix_id:'foreign',patch_sha256:'hash'}]),/не соответствует/);
 assert.match(targetError(t,bugs,fixes,[{id:'old',fix_id:'f',patch_sha256:'other'}]),/не соответствует/);
 assert.match(targetError(t,bugs,[{id:'f',bug_id:'b',verification_id:'new'}],[{id:'old',fix_id:'f'}]),/не соответствует/);
});
