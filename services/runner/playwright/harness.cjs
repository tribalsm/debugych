// Runs only inside a disposable, non-root gVisor container.
const fs=require('node:fs'), path=require('node:path'), cp=require('node:child_process');
const {createCoverageMap}=require('istanbul-lib-coverage');
const root='/tmp/job', reports=root+'/reports';
const MAX=400000;
function read(filename,max=MAX) {
  const stat=fs.lstatSync(filename);
  if(!stat.isFile()||stat.isSymbolicLink()||stat.size>max) throw Error('Unsafe or oversized report');
  return fs.readFileSync(filename);
}
async function main(job) {
  const started=Date.now();
  for(const dir of ['project','tests','reports']) fs.mkdirSync(root+'/'+dir,{recursive:true});
  for(const source of job.files) {
    const dest=path.resolve(root+'/project',source.path);
    if(!dest.startsWith(root+'/project/')) throw Error('Unsafe path');
    fs.mkdirSync(path.dirname(dest),{recursive:true});fs.writeFileSync(dest,source.content);
  }
  fs.symlinkSync('/opt/runtime/node_modules',root+'/node_modules','dir');
  const ids={};
  for(const t of job.tests) {
    const filename='test_'+t.id.replaceAll('-','')+'.spec.ts';ids[filename]=t.id;
    // Standard Playwright API, with automatic bounded screenshot/observation fixtures.
    const code=t.code.replace(/(['"])@playwright\/test\1/g,"'/opt/runtime/fixtures.cjs'");
    fs.writeFileSync(root+'/tests/'+filename,code);
  }
  fs.writeFileSync(root+'/playwright.config.cjs',`module.exports={globalSetup:'/opt/runtime/browser-setup.cjs',testDir:'./tests',workers:1,fullyParallel:false,retries:0,forbidOnly:true,timeout:7000,globalTimeout:35000,maxFailures:20,expect:{timeout:2500},outputDir:'./reports/results',reporter:[['json',{outputFile:'./reports/report.json'}]],use:{baseURL:'http://127.0.0.1:4173',browserName:'chromium',headless:true,viewport:{width:960,height:640},actionTimeout:3000,navigationTimeout:5000,serviceWorkers:'block',launchOptions:{chromiumSandbox:false,args:['--disable-dev-shm-usage','--disable-gpu','--disable-background-networking']}}};`);
  const env={PATH:'/usr/local/bin:/usr/bin:/bin',HOME:'/tmp',TMPDIR:'/tmp',LANG:'C.UTF-8',PLAYWRIGHT_BROWSERS_PATH:'/opt/browsers',NODE_OPTIONS:'--max-old-space-size=256'};
  if(job.phase==='validate') {
    try {
      const esbuild=require('esbuild');
      for(const t of job.tests) esbuild.transformSync(t.code,{loader:'ts'});
      for(const f of job.files.filter(f=>/\.(js|mjs|cjs|jsx|ts|tsx)$/.test(f.path)))
        esbuild.transformSync(f.content,{loader:f.path.endsWith('tsx')?'tsx':f.path.endsWith('jsx')?'jsx':f.path.endsWith('ts')?'ts':'js'});
    } catch {return {status:'completed',cases:[],validation:{syntax:false,discovery:false,kind:'syntax_error',collected:[]}};}
    const listing=cp.spawnSync('node',['/opt/runtime/node_modules/@playwright/test/cli.js','test','--config',root+'/playwright.config.cjs','--list'],{cwd:root,env,encoding:'utf8',timeout:15000,maxBuffer:1000000});
    let collected=[],errors=[];
    try {
      const report=JSON.parse(read(reports+'/report.json',1000000));errors=report.errors||[];
      function scan(s) {
        for(const spec of s.specs||[]) collected.push({test_id:ids[path.basename(spec.file||s.file||'')],name:spec.title});
        for(const child of s.suites||[])scan(child);
      }
      for(const s of report.suites||[])scan(s);
    } catch {errors=['Missing collection report'];}
    const valid=listing.status===0&&!errors.length&&collected.length>0&&collected.every(c=>c.test_id);
    return {status:'completed',cases:[],logs:((listing.stderr||'')+(listing.stdout||'')).slice(-12000),validation:{syntax:true,discovery:valid,kind:valid?'valid':'invalid_test',collected}};
  }
  const log=fs.openSync(reports+'/browser.log','w');
  const server=cp.spawn('node',['/opt/runtime/server.cjs'],{cwd:root,env,stdio:['ignore',log,log]});
  try {
    for(let attempt=0;;attempt++) {
      if(server.exitCode!==null||attempt>=100) throw Error('Browser site build/start failed: '+read(reports+'/browser.log',1000000).toString().slice(-1000));
      try {const res=await fetch('http://127.0.0.1:4173/');if(res.ok) break;} catch {}
      await new Promise(r=>setTimeout(r,100));
    }
    const exit=await new Promise((resolve,reject)=>{
      const child=cp.spawn('node',['/opt/runtime/node_modules/@playwright/test/cli.js','test','--config',root+'/playwright.config.cjs'],{cwd:root,env,stdio:['ignore',log,log]});
      const timer=setTimeout(()=>{child.kill('SIGKILL');reject(Error('Playwright exceeded 40 second deadline'));},40000);
      child.on('error',reject);child.on('close',code=>{clearTimeout(timer);resolve(code);});
    });
    const report=JSON.parse(read(reports+'/report.json',1000000));
    const cases=[], artifacts=[];
    function walk(suite) {
      for(const spec of suite.specs||[]) for(const test of spec.tests||[]) {
        const result=test.results?.[0];if(!result) continue;
        const testId=ids[path.basename(spec.file||suite.file||'')];if(!testId) throw Error('Unknown test in report');
        let status=result.status==='passed'?'passed':result.status==='skipped'?'skipped':result.status==='failed'?'failed':'error';
        let errors=(result.errors||[]).map(e=>e.message||e.value||'').join('\n').replace(/\u001b\[[0-9;]*m/g,'');
        if(['strict mode violation','TargetClosedError','browserType.launch'].some(marker=>errors.includes(marker))) status='error';
        if(test.expectedStatus&&test.expectedStatus!=='passed') {status='error';errors+='\nNonstandard expected status: '+test.expectedStatus;}
        for(const a of result.attachments||[]) if(a.name==='browser-observations'&&a.body&&a.body.length<=50000) {
          try {const data=JSON.parse(Buffer.from(a.body,'base64'));if(data.page_errors?.length) {status='error';errors+='\nBrowser runtime error: '+data.page_errors.join('\n');}} catch {}
        }
        cases.push({name:spec.title.slice(0,300),classname:(suite.title||'').slice(0,400),test_id:testId,status,traceback:errors.slice(0,12000),duration:(result.duration||0)/1000});
        for(const attachment of result.attachments||[]) {
          if(artifacts.length>=8) continue;
          try {
            let raw;
            if(attachment.body&&attachment.body.length<=560000) raw=Buffer.from(attachment.body,'base64');
            else if(attachment.path) {
              const dest=path.resolve(attachment.path);
              if(!dest.startsWith(reports+'/')) continue;
              raw=read(dest);
            } else continue;
            if(raw.length>MAX) continue;
            if(attachment.contentType==='image/png'&&raw.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))) {
              if(artifacts.reduce((sum,a)=>sum+a.data.length,0)+Math.ceil(raw.length*4/3)<=1600000)
                artifacts.push({name:`screenshot-${artifacts.length+1}.png`,media_type:'image/png',data:raw.toString('base64'),test_id:testId,case_name:spec.title.slice(0,300)});
            }
          } catch {}
        }
      }
      for(const child of suite.suites||[]) walk(child);
    }
    for(const suite of report.suites||[]) walk(suite);
    if(cases.length>1000) throw Error('Too many cases');
    const globalErrors=(report.errors||[]).map(e=>e.message||'').join('\n').slice(0,3000);
    const completed=[0,1].includes(exit)&&cases.length>0&&!globalErrors;
    const stats={};for(const status of ['passed','failed','error','skipped']) stats[status]=cases.filter(c=>c.status===status).length;
    const normalized={framework:'playwright',browser:'chromium',cases,errors:globalErrors,stats,raw_playwright_stats:report.stats,coverage_scope:'instrumented project JavaScript, not original TypeScript lines; dependencies excluded'};
    // Include bounded browser console observations in the downloaded JSON report.
    normalized.browser_observations=[];
    function observations(s) {for(const spec of s.specs||[]) for(const t of spec.tests||[]) for(const r of t.results||[]) for(const a of r.attachments||[]) {
      if(a.name==='browser-observations'&&a.body&&normalized.browser_observations.length<40) {
        try {normalized.browser_observations.push({test_id:ids[path.basename(spec.file||s.file||'')],case_name:spec.title,...JSON.parse(Buffer.from(a.body,'base64'))});} catch {}
      }
    } for(const child of s.suites||[]) observations(child);}
    for(const suite of report.suites||[]) observations(suite);
    const raw=Buffer.from(JSON.stringify(normalized));
    if(raw.length<=MAX) artifacts.push({name:'playwright-report.json',media_type:'application/json',data:raw.toString('base64')});
    let coverage=null;
    const map=createCoverageMap({});
    for(const name of fs.readdirSync(reports).filter(n=>/^coverage-[a-f0-9]+\.json$/.test(n)).slice(0,100)) {
      map.merge(JSON.parse(read(reports+'/'+name,1000000)));
    }
    if(map.files().length) {
      const summary=map.getCoverageSummary();const files={};
      for(const name of map.files().slice(0,100)) {
        if(name.startsWith('/')||name.includes('..')) continue;
        const lines=map.fileCoverageFor(name).getLineCoverage();
        files[name]={executed_lines:Object.keys(lines).filter(l=>lines[l]>0).map(Number),missing_lines:Object.keys(lines).filter(l=>!lines[l]).map(Number)};
      }
      coverage={totals:{percent_covered:summary.lines.pct==='Unknown'?0:summary.lines.pct,covered_lines:summary.lines.covered,num_statements:summary.lines.total,covered_branches:summary.branches.covered,num_branches:summary.branches.total},files};
      const data=Buffer.from(JSON.stringify(map.toJSON()));
      if(data.length<=MAX) artifacts.push({name:'coverage-istanbul.json',media_type:'application/json',data:data.toString('base64')});
    }
    return {status:completed?'completed':'failed',failure_kind:completed?null:'test_collection_or_infrastructure',error:completed?null:(globalErrors||'Playwright did not complete'),exit_code:exit,duration:(Date.now()-started)/1000,cases,logs:read(reports+'/browser.log',1000000).toString().slice(-24000),coverage,coverage_kind:'istanbul-generated-js',artifacts};
  } finally {server.kill('SIGKILL');fs.closeSync(log);}
}
let input='';process.stdin.setEncoding('utf8');
process.stdin.on('data',chunk=>{
  input+=chunk;if(Buffer.byteLength(input)>8500000) process.exit(2);
  if(input.includes('\n')) {
    process.stdin.pause();
    Promise.resolve().then(()=>main(JSON.parse(input.split('\n')[0]))).catch(error=>({status:'failed',failure_kind:'harness_or_infrastructure',error:String(error).slice(0,1000),cases:[]})).then(result=>{
      process.stdout.write('DEBUGYCH_RESULT='+JSON.stringify(result)+'\n',()=>process.exit(0));
    });
  }
});
