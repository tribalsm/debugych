const {test}=require('node:test'),assert=require('node:assert/strict'),path=require('node:path'),vm=require('node:vm');
process.env.NODE_PATH=path.resolve(__dirname,'../../infra/playwright/node_modules');require('node:module').Module._initPaths();
const esbuild=require('esbuild'),{createInstrumenter}=require('istanbul-lib-instrument');
const {remapCoverage,trustedInputMap}=require('../../services/runner/playwright/coverage.cjs');
const root=path.resolve('/tmp/job/project');
function observe(name,source,invoke,loader='ts'){
 const filename=path.join(root,name),built=esbuild.transformSync(source,{loader,format:'esm',target:'es2022',sourcemap:'external',sourcefile:filename,jsxFactory:'h'});
 const instrumenter=createInstrumenter({esModules:true,coverageGlobalScope:'globalThis',coverageGlobalScopeFunc:false});
 const code=instrumenter.instrumentSync(built.code,filename+'.compiled.js',JSON.parse(built.map));
 const context=vm.createContext({exports:{},module:{exports:{}},h:()=>({})});vm.runInContext(code.replace(/export\s*\{[^}]*\};?/g,''),context);invoke(context);
 return context.__coverage__;
}
test('TypeScript coverage maps branches and uncovered lines to original source, excluding erased types',async()=>{
 const source='type Amount = number;\nexport function price(n: Amount): number {\n  if (n > 0) {\n    return n * 2;\n  }\n  return 0;\n}\n';
 const raw=observe('price.ts',source,exports=>exports.price(3));const mapped=await remapCoverage(raw,{'price.ts':source},root);
 assert.equal(mapped.kind,'istanbul-original-source');assert.deepEqual(Object.keys(mapped.files),['price.ts']);
 assert.ok(mapped.files['price.ts'].executed_lines.includes(4));assert.ok(mapped.files['price.ts'].missing_lines.includes(6));
 assert.ok(!mapped.files['price.ts'].executed_lines.includes(1));assert.ok(mapped.map.getCoverageSummary().branches.total>0);
});
test('TSX coverage stays within original line bounds',async()=>{
 const source='type Props = {active: boolean};\nexport function View(p: Props) {\n  return p.active ? <h1>Ready</h1> : <p>Wait</p>;\n}\n';
 const mapped=await remapCoverage(observe('View.tsx',source,exports=>exports.View({active:true}),'tsx'),{'View.tsx':source},root);
 assert.deepEqual(Object.keys(mapped.files),['View.tsx']);assert.ok(mapped.files['View.tsx'].executed_lines.includes(3));
 assert.ok(mapped.map.getCoverageSummary().branches.pct<100);
});
test('missing or forged mapping cannot claim original source coverage',async()=>{
 await assert.rejects(remapCoverage({'generated.js':{path:'generated.js',statementMap:{},fnMap:{},branchMap:{},s:{},f:{},b:{}}},{}),/Missing input source map/);
 const source='export const x: number = 1;';const raw=observe('private.ts',source,()=>{});
 await assert.rejects(remapCoverage(raw,{'other.ts':source},root),/Unknown mapped source/);
 const filename=path.join(root,'private.ts');
 assert.throws(()=>trustedInputMap({sources:['/etc/passwd'],sourcesContent:[source]},filename,source),/source identity/);
 assert.throws(()=>trustedInputMap({sources:[filename],sourcesContent:['different source']},filename,source),/source identity/);
});
