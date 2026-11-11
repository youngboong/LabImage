(() => {
  let selected=new Set(),currentDataset=null,generation=0,mask=null,tintedColor=null;
  let pickEpoch=0,pickQueue=Promise.resolve(),pendingPicks=0;
  const tinted=document.createElement('canvas');
  function contrastColor(){
    // Also avoid the measurement yellow, the trace cyan and the Replaced pink so the selection never reads as one of them.
    const token=name=>getComputedStyle(document.body).getPropertyValue(name).trim();
    const colors=[$('poreColor').value,window.supplementalColor?.()??'#00cde0',token('--measure')||'#ffff00',token('--trace')||'#37e6ff','#ff5ab4'];
    const distance=color=>Math.min(...colors.map(base=>[1,3,5].reduce((sum,i)=>sum+(parseInt(color.slice(i,i+2),16)-parseInt(base.slice(i,i+2),16))**2,0)));
    return ['#ff00ff','#00ffff','#ffff00','#ff5533','#4488ff'].sort((a,b)=>distance(b)-distance(a))[0];
  }
  window.selectionColor=contrastColor;
  $('selectionLegendDot').style.background=contrastColor();
  function selectionRows(){
    document.querySelectorAll('#poreListRows tr[data-id]').forEach(row=>{
      const active=selected.has(Number(row.dataset.id));
      row.classList.toggle('selected',active);row.setAttribute('aria-selected',String(active));
    });
    $('selectedPoreCount').textContent=selected.size+' selected';
    const boundary=(state?.candidates??[]).filter(row=>row.touches_image_edge).map(row=>row.candidate_id);
    const boundarySelected=boundary.length>0&&boundary.length===selected.size&&boundary.every(id=>selected.has(id));
    $('selectBoundaryPores').classList.toggle('active',boundarySelected);
    $('selectBoundaryPores').setAttribute('aria-pressed',String(boundarySelected));
  }
  async function renderSelection(centerId=null){
    const version=++generation;mask=null;tintedColor=null;selectionRows();draw();controls();
    if(!state||!selected.size){$('poreSelectionInfo').textContent='No selection';return}
    const dataset=state.dataset,revision=state.revision,ids=[...selected];
    $('poreSelectionInfo').textContent=ids.length+' objects selected';
    if(ids.length===1){
      const row=state.candidates.find(c=>c.candidate_id===ids[0]);
      if(row)$('poreSelectionInfo').textContent='#'+ids[0]+': '+row.area_um2.toFixed(2)+' µm², diameter '+row.equivalent_diameter_um.toFixed(2)+' µm, roundness '+(row.roundness==null?'—':row.roundness.toFixed(3));
    }
    try{
      const result=await api('object-highlight',{dataset,revision,candidate_ids:ids});
      const loaded=await image(result.image);
      if(version!==generation||state?.dataset!==dataset||state?.revision!==revision)return;
      mask=loaded;draw();
      if(centerId!==null){
        const row=state.candidates.find(c=>c.candidate_id===centerId);
        if(row){
          const scale=canvas.getBoundingClientRect().width/canvas.width;
          for(const view of [$('viewport'),$('originalViewport')])view.scrollTo(Math.max(0,row.centroid_x_pixels*scale-view.clientWidth/2),Math.max(0,row.centroid_y_pixels*scale-view.clientHeight/2));
        }
      }
    }catch(error){if(version===generation)setStatus(error.message,true)}
  }
  function clearSelection(){pickEpoch++;selected.clear();renderSelection()}
  function selectPore(id,toggle=false,center=true){
    if(selected.has(id))selected.delete(id);
    else if(toggle)selected.add(id);
    else selected=new Set([id]);
    return renderSelection(center&&selected.has(id)?id:null);
  }
  window.drawSelectedPore=context=>{
    if(!mask)return;
    const color=contrastColor(),r=Math.max(2,Math.round(2*canvas.width/(canvas.getBoundingClientRect().width||canvas.width))); // 2 screen px
    if(color+r!==tintedColor){
      // Outline, not a fill, so the selected feature stays visible: dilate the mask, then cut the mask out.
      tinted.width=canvas.width;tinted.height=canvas.height;
      const c=tinted.getContext('2d');
      for(let a=0;a<16;a++)c.drawImage(mask,Math.round(r*Math.cos(a*Math.PI/8)),Math.round(r*Math.sin(a*Math.PI/8)));
      c.globalCompositeOperation='destination-out';c.drawImage(mask,0,0);
      c.globalCompositeOperation='source-in';c.fillStyle=color;c.fillRect(0,0,tinted.width,tinted.height);c.globalCompositeOperation='source-over';tintedColor=color+r;
    }
    $('poreDetailsDialog').style.setProperty('--highlight-color',color);$('selectionLegendDot').style.background=color;
    context.drawImage(tinted,0,0);
  };
  window.onPoreListState=data=>{
    pickEpoch++;generation++;mask=null;
    const existing=new Set(data.candidates.map(c=>c.candidate_id));
    selected=currentDataset!==data.dataset?new Set():new Set([...selected].filter(id=>existing.has(id)));
    currentDataset=data.dataset;renderSelection();
  };
  window.selectPoreFromDetails=(id,toggle=false,center=true)=>{
    if(!busy&&state?.candidates.some(c=>c.candidate_id===id)){pickEpoch++;selectPore(id,toggle,center)}
  };
  window.getSelectedPores=()=>[...selected].sort((a,b)=>a-b);
  window.getHighlightedPore=()=>selected.values().next().value??null;
  window.isPoreSelectionPending=()=>pendingPicks>0;
  // The Particle tool reuses this click-to-select (Select particles and Edit lines); onEmpty runs instead of clearing when nothing is hit.
  const picking=()=>mode==='select'||mode==='particle';
  window.pickPoreAtPoint=(point,toggle=false,onEmpty=null)=>{
    const epoch=pickEpoch,dataset=state.dataset,revision=state.revision;
    pendingPicks++;controls();
    // Keep rapid Ctrl-clicks in input order, even if requests finish at different times.
    pickQueue=pickQueue.then(async()=>{
      if(epoch!==pickEpoch||state?.dataset!==dataset||state?.revision!==revision||!picking()||busy)return;
      const result=await api('object-at-point',{dataset,revision,point});
      if(epoch!==pickEpoch||state?.dataset!==dataset||state?.revision!==revision||!picking()||busy)return;
      if(result.candidate_id===null){if(onEmpty&&!toggle)return onEmpty(point);if(!toggle){selected.clear();await renderSelection()}return}
      await selectPore(result.candidate_id,toggle,false);
      if(epoch===pickEpoch&&picking())setStatus(selected.size+(mode==='particle'?' selected':' objects selected'));
    }).catch(error=>{if(epoch===pickEpoch)setStatus(error.message,true)}).finally(()=>{pendingPicks--;controls()});
    return pickQueue;
  };
  window.clearPoreHighlight=clearSelection;
  $('clearPoreSelection').onclick=clearSelection;
  $('selectBoundaryPores').onclick=()=>{
    if(busy||!state)return;
    if(mode!=='select')document.querySelector('[data-mode="select"]').click();
    pickEpoch++;selected=new Set(state.candidates.filter(c=>c.touches_image_edge).map(c=>c.candidate_id));
    if(selected.size)$('fitComparison').click();
    renderSelection();setStatus(selected.size?'Boundary objects: '+selected.size+' selected':'No objects touch the analysis image boundary.');
  };
})();
