let value: number = 0;
document.querySelector('#increment')!.addEventListener('click', () => {
  value -= 1; // Deliberate fixture defect: requirement specifies increment.
  document.querySelector('#value')!.textContent = String(value);
  console.log('Counter updated', value);
});
