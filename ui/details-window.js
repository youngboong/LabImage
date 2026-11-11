const $=id=>document.getElementById(id);
let state=null,busy=false,selection=[],knownKey=null,exporting=false,polling=false;
window.isDetachedDetails=true;
const payload=()=>({dataset:state.dataset,revision:state.revision});
window.getSelectedPores=()=>selection;
window.getHighlightedPore=()=>selection[0]??null;
// Own status line, so errors neither overwrite the selection text nor look neutral.
const detailsStatus=Object.assign(document.createElement('p'),{id:'detailsStatus',className:'hint'});detailsStatus.setAttribute('role','status');
$('poreSelectionInfo').parentElement.after(detailsStatus);
function setStatus(message,error=false){detailsStatus.textContent=message;detailsStatus.classList.toggle('error',error)}
async function api(route,data){
  const response=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-Object-Editor':'1'},body:JSON.stringify(data)});
  const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed');return result;
}
function controls(){document.querySelectorAll('button,select,input').forEach(e=>e.disabled=busy||!state);window.updateColumnControls?.()}
async function work(message,fn){if(busy||!state)return;exporting=true;busy=true;controls();setStatus(message);try{await fn();if(detailsStatus.textContent===message)setStatus('')}catch(error){setStatus(error.message,true)}finally{exporting=false;busy=false;await synchronize()}}
async function select(id,toggle=false){
  if(busy||!state)return;
  try{await window.pywebview.api.select_details_pore(state.dataset,state.revision,id,toggle);await synchronize()}catch(error){setStatus(error.message,true)}
}
window.selectPoreFromDetails=select;
window.clearPoreHighlight=()=>select(null);
document.addEventListener('keydown',event=>{
  if(busy||!state||event.repeat||event.altKey||event.shiftKey)return;
  if(event.target instanceof Element&&(event.target.closest('input,textarea,select')||event.target.isContentEditable))return;
  const undo=(event.ctrlKey||event.metaKey)&&event.key.toLowerCase()==='z';
  if(!undo&&(event.key!=='Delete'||event.ctrlKey||event.metaKey))return;
  event.preventDefault();window.pywebview.api.details_key(state.dataset,state.revision,undo?'Undo':'Delete').catch(error=>setStatus(error.message,true));
});
async function synchronize(){
  if(polling||!window.pywebview?.api)return;
  polling=true;
  try{
    const next=await window.pywebview.api.details_state(knownKey);
    busy=exporting||next.busy;selection=next.selected;
    $('poreDetailsDialog').style.setProperty('--highlight-color',next.color);
    if(next.key!==knownKey){
      knownKey=next.key;state=next.data;
      window.renderPoreDetails(state??{dataset:null,candidates:[],stats:{candidate_union_area_percent:0}});
    }
    document.querySelectorAll('#poreListRows tr[data-id]').forEach(row=>{
      const selected=selection.includes(Number(row.dataset.id));row.classList.toggle('selected',selected);row.setAttribute('aria-selected',String(selected));
    });
    const title=window.detailsTitle?.()??'Object details'; // "Particle Details" when the rows are particles (object-details.js)
    $('poreDetailsTitle').textContent=next.stale?title+': open them again from the editor to update':title;
    controls();
  }catch(error){setStatus(error.message,true)}finally{polling=false}
}
window.addEventListener('pywebviewready',()=>{
  $('poreDetailsDialog').show();$('clearPoreSelection').onclick=()=>select(null);
  synchronize();setInterval(synchronize,400);
});
