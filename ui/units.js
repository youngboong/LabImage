// Unit conversion for application-generated labels; input values stay untouched.
window.labUnit=()=>typeof state!=='undefined'?(state?.measurement_unit??state?.stats?.measurement_unit??'px'):'px';
window.labUnitText=text=>String(text).replaceAll('µm',window.labUnit());
(()=>{
  const originals=new WeakMap();let scheduled=false;
  window.labUpdateUnits=()=>{
    scheduled=false;
    for(const root of document.querySelectorAll('#editorPanel,#poreDetailsDialog')){
      const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);let node;
      while((node=walker.nextNode())){
        if(node.parentElement?.closest('input,textarea,script,style'))continue;
        const previous=originals.get(node),value=node.nodeValue;
        const source=previous&&value===previous.rendered?previous.source:value;
        if(!source.includes('µm'))continue;
        const rendered=window.labUnitText(source);originals.set(node,{source,rendered});
        if(rendered!==value)node.nodeValue=rendered;
      }
    }
  };
  new MutationObserver(()=>{if(!scheduled){scheduled=true;requestAnimationFrame(window.labUpdateUnits)}}).observe(document.documentElement,{subtree:true,childList:true,characterData:true});
})();
