/** Deliberately small Markdown subset. No HTML parser, URL, style or script sinks. */
export function renderSafeMessage(doc:Document,text:string):HTMLElement{
 const body=doc.createElement('div');body.className='message-body';let code:string[]|null=null;let paragraph:string[]=[];let list:HTMLUListElement|HTMLOListElement|null=null;
 const inline=(el:HTMLElement,s:string)=>{const parts=s.split(/(`[^`\n]+`)/g);for(const p of parts){if(p.startsWith('`')&&p.endsWith('`')){const c=doc.createElement('code');c.textContent=p.slice(1,-1);el.append(c);}else el.append(doc.createTextNode(p));}};
 const flush=()=>{if(paragraph.length){const p=doc.createElement('p');inline(p,paragraph.join('\n'));body.append(p);paragraph=[];}list=null;};
 const flushCode=()=>{const pre=doc.createElement('pre'),c=doc.createElement('code');c.textContent=(code??[]).join('\n');pre.append(c);body.append(pre);code=null;};
 for(const line of text.slice(0,6000).split('\n')){
  if(/^\s*```/.test(line)){flush();if(code)flushCode();else code=[];continue;}
  if(code){code.push(line);continue;}
  const item=line.match(/^\s*(?:([-*]) |(\d+)\. )(.*)$/);
  if(item){if(paragraph.length)flush();const tag=item[2]?'OL':'UL';if(!list||list.tagName!==tag){list=doc.createElement(tag.toLowerCase()) as HTMLUListElement|HTMLOListElement;body.append(list);}const li=doc.createElement('li');inline(li,item[3]);list.append(li);continue;}
  if(!line.trim()){flush();continue;}
  if(list)list=null;paragraph.push(line);
 }
 flush();if(code)flushCode();return body;
}
