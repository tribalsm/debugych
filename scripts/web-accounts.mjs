// Account records contain password hashes and hashed session/invitation IDs only.
import {DatabaseSync} from 'node:sqlite';
import {randomBytes,scrypt as derive,timingSafeEqual,createHash} from 'node:crypto';
import {promisify} from 'node:util';
import {mkdirSync,chmodSync} from 'node:fs';
import path from 'node:path';
const scrypt=promisify(derive),digest=value=>createHash('sha256').update(value).digest('hex');
const roles=new Set(['viewer','jury','team','admin']);
export class AccountError extends Error{constructor(status,message){super(message);this.status=status}}
export class Accounts{
 constructor(filename,{now=Date.now}={}){
  this.now=now;this.kdfBusy=0;
  if(filename!==':memory:'){mkdirSync(path.dirname(filename),{recursive:true,mode:0o700});}
  this.db=new DatabaseSync(filename);if(filename!==':memory:')chmodSync(filename,0o600);
  this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=3000;
   CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,username TEXT UNIQUE NOT NULL,password TEXT NOT NULL,role TEXT NOT NULL CHECK(role IN ('viewer','jury','team','admin')),active INTEGER NOT NULL DEFAULT 1,version INTEGER NOT NULL DEFAULT 1,created INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),version INTEGER NOT NULL,created INTEGER NOT NULL,seen INTEGER NOT NULL,expires INTEGER NOT NULL);
   CREATE TABLE IF NOT EXISTS invitations(hash TEXT PRIMARY KEY,role TEXT NOT NULL,expires INTEGER NOT NULL,used INTEGER NOT NULL DEFAULT 0,created INTEGER NOT NULL,created_by TEXT NOT NULL);`);
  if(!this.db.prepare('PRAGMA table_info(users)').all().some(c=>c.name==='must_change'))this.db.exec('ALTER TABLE users ADD COLUMN must_change INTEGER NOT NULL DEFAULT 0');
 }
 async derive(password,salt){
  if(this.kdfBusy>=2)throw new AccountError(429,'Слишком много запросов. Повторите позднее.');this.kdfBusy++;
  try{return await scrypt(password,salt,64,{N:32768,r:8,p:1,maxmem:64*1024*1024})}finally{this.kdfBusy--}
 }
 username(value){if(typeof value!=='string'||!/^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,39}$/.test(value))throw new AccountError(400,'Логин: 3-40 латинских букв, цифр, точек, дефисов или подчёркиваний.');return value.toLowerCase()}
 password(value){if(typeof value!=='string'||[...value].length<12||[...value].length>128||Buffer.byteLength(value)>512)throw new AccountError(400,'Пароль должен содержать от 12 до 128 символов.');return value}
 async register({username,password,profile='viewer',invitation=''},{reserved=false}={}){
  username=this.username(username);password=this.password(password);
  if(!reserved&&['jury','debugych-jury','team-admin','debugych-team'].includes(username))throw new AccountError(409,'Этот логин зарезервирован. Выберите личный логин.');
  if(!['viewer','jury'].includes(profile))throw new AccountError(403,'Для рабочего доступа требуется приглашение.');
  if(typeof invitation!=='string'||invitation.length>256)throw new AccountError(400,'Некорректное приглашение.');
  const salt=randomBytes(16).toString('hex'),key=await this.derive(password,salt),encoded=`scrypt$32768$8$1$${salt}$${key.toString('hex')}`;
  const id=randomBytes(16).toString('hex');
  this.db.exec('BEGIN IMMEDIATE');
  try{
   if(this.db.prepare('SELECT count(*) AS n FROM users').get().n>=1000)throw new AccountError(503,'Регистрация временно приостановлена.');
   let role=profile;
   if(invitation){const grant=this.db.prepare('SELECT * FROM invitations WHERE hash=?').get(digest(invitation));if(!grant||grant.used||grant.expires<=this.now())throw new AccountError(400,'Приглашение недействительно или уже использовано.');role=grant.role;}
   if(this.db.prepare('SELECT id FROM users WHERE username=?').get(username))throw new AccountError(409,'Этот логин недоступен.');
   this.db.prepare('INSERT INTO users(id,username,password,role,created) VALUES(?,?,?,?,?)').run(id,username,encoded,role,this.now());
   if(invitation)this.db.prepare('UPDATE invitations SET used=1 WHERE hash=?').run(digest(invitation));
   this.db.exec('COMMIT');return {id,username,role};
  }catch(e){this.db.exec('ROLLBACK');throw e}
 }
 async login(username,password){
  if(typeof password!=='string'||Buffer.byteLength(password)>512)throw new AccountError(401,'Неверный логин или пароль.');
  let name;try{name=this.username(username)}catch{ name='__invalid__'; }
  const user=this.db.prepare('SELECT * FROM users WHERE username=?').get(name);
  // Missing users perform the same expensive derivation to reduce enumeration.
  const encoded=user?.password||'scrypt$32768$8$1$'+'0'.repeat(32)+'$'+'0'.repeat(128);
  const parts=encoded.split('$'),key=await this.derive(password,parts[4]),expected=Buffer.from(parts[5],'hex');
  if(!user||!user.active||expected.length!==key.length||!timingSafeEqual(expected,key))throw new AccountError(401,'Неверный логин или пароль.');
  return {id:user.id,username:user.username,role:user.role,mustChange:!!user.must_change};
 }
 createSession(userId){
  const user=this.db.prepare('SELECT * FROM users WHERE id=? AND active=1').get(userId);if(!user)throw new AccountError(401,'Аккаунт недоступен.');
  this.cleanup();if(this.db.prepare('SELECT count(*) AS n FROM sessions').get().n>=512)throw new AccountError(503,'Лимит сеансов. Повторите позднее.');
  const value=randomBytes(32).toString('hex'),now=this.now();
  this.db.prepare('INSERT INTO sessions(hash,user_id,version,created,seen,expires) VALUES(?,?,?,?,?,?)').run(digest(value),userId,user.version,now,now,now+8*3600000);return value;
 }
 async changePassword(id,current,newPassword){
  const before=this.db.prepare('SELECT * FROM users WHERE id=? AND active=1').get(id);if(!before)throw new AccountError(401,'Аккаунт недоступен.');
  await this.login(before.username,current);this.password(newPassword);const salt=randomBytes(16).toString('hex'),key=await this.derive(newPassword,salt);
  const value=`scrypt$32768$8$1$${salt}$${key.toString('hex')}`;
  const result=this.db.prepare('UPDATE users SET password=?,version=version+1,must_change=0 WHERE id=? AND version=? AND active=1').run(value,id,before.version);if(!result.changes)throw new AccountError(409,'Аккаунт изменился. Войдите снова.');
  this.db.prepare('DELETE FROM sessions WHERE user_id=?').run(id);
 }
 session(hash){
  const row=this.db.prepare('SELECT u.id,u.username,u.role,u.active,u.version,u.must_change,s.version AS session_version,s.expires,s.seen FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.hash=?').get(hash);
  if(!row)return null;
  if(!row.active||row.version!==row.session_version||row.expires<=this.now()||row.seen+30*60000<=this.now()){this.deleteSession(hash);return null;}
  this.db.prepare('UPDATE sessions SET seen=? WHERE hash=?').run(this.now(),hash);return {id:row.id,username:row.username,role:row.role,mustChange:!!row.must_change};
 }
 deleteSession(hash){this.db.prepare('DELETE FROM sessions WHERE hash=?').run(hash)}
 createInvitation(role,actor){if(!roles.has(role))throw new AccountError(400,'Неизвестная роль.');this.cleanup();if(this.db.prepare('SELECT count(*) AS n FROM invitations').get().n>=256)throw new AccountError(429,'Лимит приглашений.');const value=randomBytes(32).toString('hex');this.db.prepare('INSERT INTO invitations(hash,role,expires,created,created_by) VALUES(?,?,?,?,?)').run(digest(value),role,this.now()+72*3600000,this.now(),actor);return value}
 users(){return this.db.prepare('SELECT id,username,role,active,created FROM users ORDER BY created DESC').all()}
 changeUser(id,role,active,actor){
  if(!roles.has(role)||![0,1].includes(active))throw new AccountError(400,'Некорректные права.');if(id===actor)throw new AccountError(409,'Собственные права меняет другой администратор.');
  const result=this.db.prepare('UPDATE users SET role=?,active=?,version=version+1 WHERE id=?').run(role,active,id);if(!result.changes)throw new AccountError(404,'Аккаунт не найден.');
  this.db.prepare('DELETE FROM sessions WHERE user_id=?').run(id);
 }
 cleanup(){this.db.prepare('DELETE FROM sessions WHERE expires<=? OR seen<=?').run(this.now(),this.now()-30*60000);this.db.prepare('DELETE FROM invitations WHERE expires<=? OR used=1').run(this.now())}
 close(){this.db.close()}
}
