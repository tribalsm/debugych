import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp,readFile,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';
import {Accounts} from '../../scripts/web-accounts.mjs';
const password='Offline-test-password-123!',hash=s=>createHash('sha256').update(s).digest('hex');
test('registration, roles, single-use grants, password/session revocation and persistence',async()=>{
 const root=await mkdtemp(path.join(tmpdir(),'debugych-accounts-')),file=path.join(root,'users.sqlite');let clock=10000,store=new Accounts(file,{now:()=>clock});
 try{
  const viewer=await store.register({username:'Viewer',password});assert.equal(viewer.role,'viewer');assert.equal((await store.login('VIEWER',password)).id,viewer.id);
  const jury=await store.register({username:'jury-control',password,profile:'jury'});assert.equal(jury.role,'jury');
  await assert.rejects(store.register({username:'escalation',password,profile:'admin'}),e=>e.status===403);
  await assert.rejects(store.register({username:'viewer',password}),e=>e.status===409);
  await assert.rejects(store.register({username:'bad<script>',password}),e=>e.status===400);
  await assert.rejects(store.register({username:'short',password:'tiny'}),e=>e.status===400);
  await assert.rejects(store.login('viewer','incorrect'),e=>e.status===401);
  await assert.rejects(store.login('missing',password),e=>e.status===401);
  const invitation=store.createInvitation('team','owner-key');
  const member=await store.register({username:'member',password,invitation});assert.equal(member.role,'team');
  await assert.rejects(store.register({username:'reuse',password,invitation}),e=>e.status===400);
  const expire=store.createInvitation('admin','owner-key');clock+=73*3600000;
  await assert.rejects(store.register({username:'expired',password,invitation:expire}),e=>e.status===400);
  const session=store.createSession(member.id);assert.equal(store.session(hash(session)).role,'team');
  store.close();store=new Accounts(file,{now:()=>clock});assert.equal(store.session(hash(session)).username,'member');
  store.changeUser(member.id,'jury',1,'owner-key');assert.equal(store.session(hash(session)),null);assert.equal((await store.login('member',password)).role,'jury');
  store.db.prepare('UPDATE users SET must_change=1 WHERE id=?').run(jury.id);const a=store.createSession(jury.id),b=store.createSession(jury.id);assert.equal(store.session(hash(a)).mustChange,true);await store.changePassword(jury.id,password,'New-offline-password-456!');assert.equal(store.session(hash(a)),null);assert.equal(store.session(hash(b)),null);assert.equal((await store.login(jury.username,'New-offline-password-456!')).mustChange,false);
  await assert.rejects(store.login(jury.username,password),e=>e.status===401);await store.login(jury.username,'New-offline-password-456!');
  store.changeUser(viewer.id,'viewer',0,'owner-key');await assert.rejects(store.login('viewer',password),e=>e.status===401);
  assert.throws(()=>store.changeUser(member.id,'admin',1,member.id),e=>e.status===409);
  const idle=store.createSession(member.id);clock+=31*60000;assert.equal(store.session(hash(idle)),null);
  assert.ok(store.users().every(u=>!Object.hasOwn(u,'password')));
  store.close();store=null;const bytes=await readFile(file);assert.ok(!bytes.includes(Buffer.from(password)));assert.ok(!bytes.includes(Buffer.from(invitation)));assert.ok(!bytes.includes(Buffer.from(session)));
 }finally{store?.close();await rm(root,{recursive:true,force:true})}
});
