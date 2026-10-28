// Operator-only bootstrap. Credentials arrive via stdin, never argv or output.
import {Accounts} from './web-accounts.mjs';
let raw='';for await(const chunk of process.stdin){raw+=chunk;if(raw.length>8192)throw Error('Provision payload too large')}
const entries=JSON.parse(raw);raw='';if(!Array.isArray(entries)||!entries.length||entries.length>4)throw Error('Invalid account count');
const store=new Accounts(process.env.ACCOUNTS_DB||'/accounts/users.sqlite');
try{
 const existing=new Set(store.users().map(u=>u.username));
 for(const entry of entries){store.username(entry.username);store.password(entry.password);if(existing.has(entry.username.toLowerCase())||!['jury','admin'].includes(entry.role))throw Error('Reserved account already exists or role is invalid')}
 const result=[];
 for(const entry of entries){const invitation=store.createInvitation(entry.role,'operator-bootstrap');const user=await store.register({username:entry.username,password:entry.password,invitation},{reserved:true});store.db.prepare('UPDATE users SET must_change=1 WHERE id=?').run(user.id);result.push({username:user.username,role:user.role,mustChange:true})}
 console.log(JSON.stringify({created:result}));
}finally{store.close()}
