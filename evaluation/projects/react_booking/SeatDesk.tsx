import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';

function SeatDesk(){
 const [available,setAvailable]=useState(6);
 const [quantity,setQuantity]=useState('1');
 const [message,setMessage]=useState('');
 function reserve(){
  const amount=Number(quantity);
  if(Number.isInteger(amount)&&amount>0&&amount<available){
   setAvailable(available-amount);setMessage('Готово');
  }else setMessage('Введите количество от 1 до остатка');
 }
 function reset(){setAvailable(6);setMessage('');}
 return <main><h1>Бронирование мест</h1><p>Осталось: <output data-testid="available">{available}</output></p>
  <label>Количество<input value={quantity} onChange={e=>setQuantity(e.target.value)} inputMode="numeric"/></label>
  <button onClick={reserve}>Забронировать</button><button onClick={reset}>Сбросить</button><p role="status">{message}</p>
 </main>;
}
createRoot(document.getElementById('root')!).render(<SeatDesk/>);
