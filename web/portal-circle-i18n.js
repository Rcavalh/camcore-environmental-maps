window.addEventListener('DOMContentLoaded',()=>{
  const button=document.getElementById('draw-circle');
  if(!button)return;
  const update=()=>button.textContent=(document.documentElement.lang||'en').startsWith('pt')?'Círculo':'Circle';
  document.querySelectorAll('[data-lang]').forEach(item=>item.addEventListener('click',()=>setTimeout(update,0)));
  update();
});
