import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';

function Invoice(){
 const [seats,setSeats]=useState('2');
 const [plan,setPlan]=useState('basic');
 const [annual,setAnnual]=useState(false);
 const [accepted,setAccepted]=useState(false);
 const [quote,setQuote]=useState('—');
 const [notice,setNotice]=useState('');
 function calculate(){
  const n=Number(seats);
  if(!Number.isInteger(n)||n<1||n>8){setNotice('Seats must be an integer from 1 to 8');return;}
  const base=n*(plan==='basic'?120:200);
  const value=annual?Math.floor((base+30)*75/100):base+30;
  setQuote(String(value));
  if(!accepted){setNotice('Accept terms');return;}
  setNotice('Ready');
 }
 return <main><h1>Team Invoice</h1>
  <label>Seats<input value={seats} onChange={e=>setSeats(e.target.value)}/></label>
  <label>Plan<select value={plan} onChange={e=>setPlan(e.target.value)}><option value="basic">Basic</option><option value="pro">Pro</option></select></label>
  <label><input type="checkbox" checked={annual} onChange={e=>setAnnual(e.target.checked)}/>Annual</label>
  <label><input type="checkbox" checked={accepted} onChange={e=>setAccepted(e.target.checked)}/>Terms</label>
  <button onClick={calculate}>Quote</button><output data-testid="quote">{quote}</output><p data-testid="notice">{notice}</p>
 </main>;
}
createRoot(document.getElementById('root')!).render(<Invoice/>);
