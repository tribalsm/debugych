import {mountPet} from './pet.js';
mountPet(document.querySelector('main')).catch(async error=>{const p=document.createElement('p');p.className='pet-error';p.textContent='Не удалось загрузить питомца: '+error.message;document.body.replaceChildren(p);if(window.__TAURI__)await window.__TAURI__.core.invoke('pet_ready');});
