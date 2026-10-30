const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const esbuild = require('esbuild');
const {createInstrumenter} = require('istanbul-lib-instrument');
const root='/tmp/job/project', site='/tmp/job/site';

async function main() {
  fs.mkdirSync(site,{recursive:true});
  const files=[];
  function walk(dir) {for(const entry of fs.readdirSync(dir,{withFileTypes:true})) {
    const filename=path.join(dir,entry.name);
    if(entry.isDirectory()) walk(filename); else files.push(path.relative(root,filename));
  }}
  walk(root);
  const entries=new Set();
  for(const name of files.filter(n=>n.endsWith('.html'))) {
    const html=fs.readFileSync(path.join(root,name),'utf8');
    for(const match of html.matchAll(/<script\b[^>]*\bsrc\s*=\s*["']([^"']+)["']/gi)) {
      if(/^(?:https?:|\/\/|data:)/i.test(match[1])) throw Error('Remote browser entries are unsupported');
      const entry=path.posix.normalize(match[1].startsWith('/')?match[1].slice(1):path.posix.join(path.posix.dirname(name),match[1]));
      if(entry.startsWith('../')||!files.includes(entry)) throw Error('Missing local browser entry: '+entry);
      entries.add(entry);
    }
  }
  const mapped = new Set();
  const styles = new Set();
  const instrumentProject={name:'instrument-project',setup(build){
    build.onLoad({filter:/\/tmp\/job\/project\/.*\.(?:[cm]?js|jsx|tsx?)$/i},async args=>{
      const extension=path.extname(args.path).slice(1);
      const loader=extension==='mjs'||extension==='cjs'?'js':extension;
      const source=fs.readFileSync(args.path,'utf8');
      const transformed=await esbuild.transform(source,{loader,format:'esm',target:'es2022',jsx:'automatic',sourcemap:'external',sourcefile:args.path});
      const name=args.path+'.compiled.js';
      const inputMap=require('./coverage.cjs').trustedInputMap(JSON.parse(transformed.map),args.path,source);
      const contents=createInstrumenter({esModules:true,compact:false,coverageGlobalScope:'globalThis',coverageGlobalScopeFunc:false}).instrumentSync(transformed.code,name,inputMap);
      return {contents,loader:'js',resolveDir:path.dirname(args.path)};
    });
  }};
  for(const name of entries) {
    if(!/\.(?:[cm]?js|jsx|tsx?)$/i.test(name)) continue;
    const output=name.replace(/\.(?:[cm]?js|jsx|tsx?)$/i,'.js');
    if(mapped.has(output)) throw Error('Ambiguous browser output: '+output);
    mapped.add(output);
    const built=await esbuild.build({entryPoints:[path.join(root,name)],outfile:path.join(site,output),bundle:true,write:false,format:'esm',platform:'browser',
      target:'es2022',define:{'process.env.NODE_ENV':'"production"'},nodePaths:['/opt/runtime/node_modules'],logLevel:'silent',jsx:'automatic',plugins:[instrumentProject]});
    const javascript=built.outputFiles.find(f=>f.path.endsWith('.js'));
    const code=javascript.text;
    const dest=path.join(site,output); fs.mkdirSync(path.dirname(dest),{recursive:true}); fs.writeFileSync(dest,code);
    for(const file of built.outputFiles.filter(f=>f.path.endsWith('.css'))) {fs.writeFileSync(file.path,file.contents);styles.add('/'+path.relative(site,file.path));}
  }
  for(const name of files) {
    if(!/\.(?:html|css|json)$/i.test(name)) continue;
    let content=fs.readFileSync(path.join(root,name),'utf8');
    if(name.endsWith('.html')) content=[...styles].map(href=>`<link rel="stylesheet" href="${href}">`).join('')+content.replace(/(\b(?:src|href)\s*=\s*["'][^"']+)\.(?:ts|tsx|jsx|mjs|cjs)(["'])/gi,'$1.js$2');
    const dest=path.join(site,name); fs.mkdirSync(path.dirname(dest),{recursive:true}); fs.writeFileSync(dest,content);
  }
  const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json'};
  http.createServer((req,res)=>{
    try {
      const pathname=decodeURIComponent(new URL(req.url,'http://127.0.0.1').pathname);
      const dest=path.resolve(site,'.'+(pathname==='/'?'/index.html':pathname));
      if(!dest.startsWith(site+'/')||!fs.statSync(dest).isFile()) throw Error('not found');
      res.setHeader('Content-Type',mime[path.extname(dest)]||'text/plain');
      res.setHeader('X-Content-Type-Options','nosniff');
      // No remote resources or connections, even from hostile uploaded HTML.
      res.setHeader('Content-Security-Policy',"default-src 'self' data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; frame-src 'none'; object-src 'none'");
      fs.createReadStream(dest).pipe(res);
    } catch {res.statusCode=404;res.end('Not found');}
  }).listen(4173,'127.0.0.1',()=>console.log('DEBUGYCH_SITE_READY'));
}
main().catch(error=>{console.error(String(error));process.exit(1);});
