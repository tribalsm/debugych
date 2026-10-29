// Browser identities and project ownership stay in the trusted gateway database.
import {randomBytes,createHash} from 'node:crypto';
import {AccountError} from './web-accounts.mjs';
const hash=v=>createHash('sha256').update(v).digest('hex');
export const GUEST_DAYS=30;
export class Workspaces{
 constructor(accounts,{now=Date.now}={}){
  this.db=accounts.db;this.now=now;
  this.db.exec(`CREATE TABLE IF NOT EXISTS guest_history(hash TEXT PRIMARY KEY,id TEXT UNIQUE NOT NULL,expires INTEGER NOT NULL,created INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS project_owners(project_id TEXT PRIMARY KEY,owner TEXT NOT NULL,guest INTEGER NOT NULL,bytes INTEGER NOT NULL DEFAULT 0);
   CREATE TABLE IF NOT EXISTS workspace_usage(scope TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,n INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(scope,day,kind));
   CREATE TABLE IF NOT EXISTS workspace_config(key TEXT PRIMARY KEY,value TEXT NOT NULL);`);
  this.db.prepare('INSERT OR IGNORE INTO workspace_config VALUES(?,?)').run('ip-salt',randomBytes(32).toString('hex'));
  this.salt=this.db.prepare('SELECT value FROM workspace_config WHERE key=?').get('ip-salt').value;
 }
 ip(req){return hash(this.salt+String(req.headers['x-real-ip']||req.socket.remoteAddress))}
 consume(scope,kind,limit){
  const day=new Date(this.now()).toISOString().slice(0,10);
  this.db.prepare('INSERT OR IGNORE INTO workspace_usage VALUES(?,?,?,0)').run(scope,day,kind);
  const changed=this.db.prepare('UPDATE workspace_usage SET n=n+1 WHERE scope=? AND day=? AND kind=? AND n<?').run(scope,day,kind,limit);
  if(!changed.changes)throw new AccountError(429,'Достигнут дневной лимит тестового режима. Войдите в аккаунт или повторите завтра.');
  this.db.prepare('DELETE FROM workspace_usage WHERE day<?').run(new Date(this.now()-7*86400000).toISOString().slice(0,10));
 }
 createGuest(req){
  if(this.db.prepare('SELECT count(*) AS n FROM guest_history WHERE expires>?').get(this.now()).n>=100)throw new AccountError(503,'Гостевой режим временно заполнен. Войдите в аккаунт.');
  this.consume('ip:'+this.ip(req),'guest-create',3);this.consume('global','guest-create',20);
  const sid=randomBytes(32).toString('hex'),id='guest-'+randomBytes(16).toString('hex'),now=this.now();
  this.db.prepare('INSERT INTO guest_history VALUES(?,?,?,?)').run(hash(sid),id,now+GUEST_DAYS*86400000,now);return sid;
 }
 session(key){
  const row=this.db.prepare('SELECT * FROM guest_history WHERE hash=? AND expires>?').get(key,this.now());if(!row)return null;
  const expires=this.now()+GUEST_DAYS*86400000;this.db.prepare('UPDATE guest_history SET expires=? WHERE hash=?').run(expires,key);
  return {id:row.id,username:row.id.slice(0,18),role:'guest',guest:true,expires};
 }
 end(key){this.db.prepare('UPDATE guest_history SET expires=? WHERE hash=?').run(this.now(),key)}
 claim(guest,user){
  if(!guest?.guest)return;
  this.db.exec('BEGIN IMMEDIATE');try{
   this.db.prepare('UPDATE project_owners SET owner=?,guest=0 WHERE owner=?').run(user.id,guest.id);
   this.db.prepare('DELETE FROM guest_history WHERE id=?').run(guest.id);this.db.exec('COMMIT');
  }catch(e){this.db.exec('ROLLBACK');throw e}
 }
 owns(s,id){return ['owner','admin'].includes(s?.role)||!!this.db.prepare('SELECT 1 FROM project_owners WHERE project_id=? AND owner=?').get(id,s?.id||'')}
 projects(s){return this.db.prepare('SELECT project_id,bytes FROM project_owners WHERE owner=?').all(s.id)}
 attach(s,id){this.db.prepare('INSERT INTO project_owners(project_id,owner,guest) VALUES(?,?,?)').run(id,s.id,s.guest?1:0)}
 remove(id){this.db.prepare('DELETE FROM project_owners WHERE project_id=?').run(id)}
 size(id,n){this.db.prepare('UPDATE project_owners SET bytes=? WHERE project_id=?').run(n,id)}
 assertCreate(s){if(this.projects(s).length>=(s.guest?3:20))throw new AccountError(429,s.guest?'В гостевой истории можно хранить до 3 проектов. Войдите, чтобы сохранить историю.':'Лимит: 20 проектов. Удалите ненужные проекты.');}
 assertUpload(s,reserved=0){
  const bytes=this.projects(s).reduce((sum,p)=>sum+p.bytes,0);
  if(bytes+30*1024*1024>(s.guest?64:256)*1024*1024)throw new AccountError(413,'Недостаточно места для загрузки. Освободите место в истории.');
  if(s.guest&&this.db.prepare('SELECT coalesce(sum(bytes),0) AS n FROM project_owners WHERE guest=1').get().n+30*1024*1024+reserved>512*1024*1024)throw new AccountError(503,'Гостевое хранилище заполнено. Войдите в аккаунт.');
 }
 reserveRun(s,req){if(s.guest){this.consume(s.id,'run',5);this.consume('ip:'+this.ip(req),'run',10);this.consume('global','guest-run',30)}else if(s.role!=='owner'&&s.role!=='admin')this.consume(s.id,'run',30)}
 expired(){return this.db.prepare('SELECT p.project_id FROM project_owners p JOIN guest_history g ON p.owner=g.id WHERE g.expires<=?').all(this.now())}
 prune(){this.db.prepare('DELETE FROM guest_history WHERE expires<=? AND NOT EXISTS(SELECT 1 FROM project_owners p WHERE p.owner=guest_history.id)').run(this.now())}
}
