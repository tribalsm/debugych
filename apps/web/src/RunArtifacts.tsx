import {useState} from 'react';
export type Artifact = {id:string;name:string;media_type:string;size:number;sha256:string;test_id?:string;case_name?:string};
export type ArtifactRun = {id:string;status:string;profile?:string;artifacts?:Artifact[]};
export function RunArtifacts({runs}:{runs:ArtifactRun[]}){
 const [selected,setSelected]=useState('');
 const choices=[...runs].reverse().filter(r=>r.artifacts?.length);
 const run=choices.find(r=>r.id===selected)||choices[0];
 if(!run)return null;
 const href=(a:Artifact)=>`/api/runs/${run.id}/artifacts/${a.id}`;
 return <section className="panel run-artifacts"><div className="panel-title"><div><h2>Браузерные отчёты и скриншоты</h2><p>Фактические артефакты gVisor · наблюдения недоверенного проекта</p></div></div>
 <label>Запуск с артефактами<select aria-label="Запуск с артефактами" value={run.id} onChange={e=>setSelected(e.target.value)}>{choices.map(r=><option key={r.id} value={r.id}>{r.id.slice(0,8)} · {r.status} · {r.profile||'Playwright'}</option>)}</select></label>
 <div className="project-actions">{run.artifacts?.filter(a=>a.media_type==='application/json').map(a=><a className="secondary" href={href(a)} key={a.id} download>{a.name}</a>)}</div>
 <div className="screenshot-grid">{run.artifacts?.filter(a=>a.media_type==='image/png').map(a=><figure key={a.id}><a href={href(a)} download><img loading="lazy" src={href(a)} alt={`Скриншот ${a.name} · ${a.case_name||'тест '+a.test_id?.slice(0,8)}`}/></a><figcaption>{a.case_name||a.name} · {(a.size/1024).toFixed(1)} КБ</figcaption><details><summary>Целостность артефакта</summary><code>SHA256: {a.sha256}</code></details></figure>)}</div>
 <p>Скриншоты автоматически снимаются после браузерного кейса, включая assertion-падения. Отсутствующий скриншот не заменяется заглушкой.</p>
 </section>
}
