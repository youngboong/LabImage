"""App-owned UI integration test, executed inside the native WebView2 window."""
import base64
import io
import json
from pathlib import Path
import time
from PIL import Image, ImageDraw


def run(window):
    im=Image.new('RGB',(320,256),'#252a32');d=ImageDraw.Draw(im)
    d.ellipse((48,58,132,142),fill='#d7cba3');d.rectangle((185,60,265,155),fill='#69bdd1')
    stream=io.BytesIO();im.save(stream,format='PNG')
    content=base64.b64encode(stream.getvalue()).decode('ascii')
    script=r'''
    window.labQaResult=null;
    (async()=>{
      const check=(condition,message)=>{if(!condition)throw new Error(message)};
      check(typeof labChoose==='function','LabImage workflow script failed');
      check(typeof window.createPoreColumnPicker==='function','Object details script failed');
      check(typeof window.openReportComposer==='function','Report composer failed');
      check(!labHome.classList.contains('hidden'),'Mode chooser not visible');
      await labChoose('report');
      const upload=await api('upload',{name:'ui-validation.png',content:CONTENT});
      await selectImage(upload);
      check(!$('setupPanel').classList.contains('hidden'),'Setup panel did not open');
      check(document.documentElement.lang==='en','Default language must be English');
      const lookChecks=()=>{
        check(!/[\uac00-\ud7a3]/.test(document.body.innerText),'Korean text in UI');
        check(getComputedStyle(document.body).backgroundColor==='rgb(233, 235, 238)','Light theme missing');
        check(getComputedStyle(document.documentElement).colorScheme==='light','Color scheme is not light');
        check(document.querySelector('header .steps'),'Stepper not in header');
      };
      lookChecks();
      check(getComputedStyle($('normalizeEnabled').closest('section')).display==='none','Report exposes preprocessing');
      check(getComputedStyle($('preprocessingImage').closest('section')).display==='none','Report exposes processed preview');
      check(!$('labCalibrated').checked,'Pixel calibration should be the default');
      check($('labSavedDialog') instanceof HTMLDialogElement,'Saved dialog element missing');
      labShowSaved(['C:/out/a(1).png','C:/out/a(2).png']);
      check($('labSavedDialog').open&&$('labSavedFolder').textContent==='C:/out'&&$('labSavedFiles').children.length===2,'Saved dialog does not list the folder and files');
      $('labSavedOk').click();check(!$('labSavedDialog').open,'Saved dialog OK does not close');
      const realApi=api;
      const drag=(type,p,button=0)=>{
        const r=canvas.getBoundingClientRect();
        canvas.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:9,button,buttons:type==='pointerup'?0:button===2?2:1,clientX:r.left+p[0]*r.width/canvas.width,clientY:r.top+p[1]*r.height/canvas.height}));
      };
      // Particles: Set up -> automatic Detect particles -> Select particles (two panes) -> Edit lines (one pane).
      // The synthetic image may make the backend answer 400, so mostly the requests are checked.
      const particleCalls=[],idle=async(n=300)=>{for(let i=0;i<n&&busy;i++)await new Promise(r=>setTimeout(r,100))};
      window.labParticleReplies=[]; // what the backend answered, for the smoke report
      api=(route,data)=>{particleCalls.push([route,data]);return realApi(route,data).then(r=>{window.labParticleReplies.push(route+': ok');return r},e=>{window.labParticleReplies.push(route+': '+e.message);throw e})};
      try{
        check($('runAnalysis').textContent==='Detect particles','Run button does not say Detect particles');
        await $('runAnalysis').onclick();await idle(900);
        check(particleCalls.some(([r])=>r==='detect-particles'),'Analysis in Particles mode did not send detect-particles: '+$('status').textContent);
        check(mode==='particle'&&document.body.dataset.particleStage==='select','Particles did not open in Select particles');
        const panes=[...document.querySelectorAll('.comparison-pane')].map(p=>getComputedStyle(p).display!=='none');
        check(panes[0]&&panes[1],'Select particles does not show two panes');
        check(/Selected particles/.test(document.querySelectorAll('.comparison-pane h2')[1].textContent),'Right pane is not labelled Selected particles');
        check(['particleNext','particleDetect','particleDetails','particleRemove'].every(id=>getComputedStyle($(id)).display!=='none'),'Next, Detect particles, Details or Remove missing in Select particles');
        lookChecks();
        drag('pointerdown',[220,100]);drag('pointerup',[220,100]);await idle();
        check(particleCalls.some(([r,d])=>r==='object-at-point'&&d.point?.length===2),'A click in Select particles did not look up the particle');
        $('particleNext').click();
        check(document.body.dataset.particleStage==='lines','Next: edit lines failed');
        check(getComputedStyle(document.querySelector('.comparison-pane')).display==='none','Edit lines must show one image');
        particleEditSet('draw');particleAxisSet('length');
        check(getComputedStyle($('particleAxis')).display!=='none'&&$('openPoreDetails').textContent.trim()==='Particle details'&&getComputedStyle($('openPoreDetails')).display!=='none','Length/Width or Details missing in Edit lines');
        drag('pointerdown',[60,100]);for(const x of [75,90,105])drag('pointermove',[x,100]);drag('pointerup',[120,100]);
        await idle();
        check(particleCalls.some(([r,d])=>r==='particle-line'&&d.axis==='length'&&d.points?.length===2&&d.points.every(p=>p.length===2)),'Draw did not send particle-line with axis length and 2 points');
        particleAxisSet('width');
        for(const p of [[90,80],[90,120]]){drag('pointerdown',p);drag('pointerup',p)}
        await idle();
        check(particleCalls.some(([r,d])=>r==='particle-line'&&d.axis==='width'&&d.points?.length===2),'Two clicks did not send a width particle-line');
        // Select a drawn line on the canvas and delete only that line.
        particleEditSet('select');
        const row=particleRows().find(r=>Array.isArray(r.length_line));
        check(row,'No length_line on the measurement rows after drawing one: '+JSON.stringify(window.labParticleReplies));
        const [a,b]=row.length_line,at=[a[0]+(b[0]-a[0])*.25,a[1]+(b[1]-a[1])*.25];
        drag('pointerdown',at);drag('pointerup',at);await idle();
        check(lineSel?.axis==='length'&&lineSel.id===row.candidate_id,'Clicking a line did not select it');
        canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',code:'Delete',bubbles:true,cancelable:true}));
        await idle();
        check(particleCalls.some(([r,d])=>r==='particle-line'&&d.points===null&&d.axis==='length'&&d.object_id===row.candidate_id),'Deleting a selected line did not send particle-line with points null');
        canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',bubbles:true,cancelable:true}));
        check(!getSelectedPores().length,'Esc did not clear the selection');
        particleEditSet('draw');particleAxisSet('length');
        drag('pointerdown',[200,200]);drag('pointermove',[240,200]);drag('pointerup',[280,200]);await idle();
        // Back to Select particles: PoreSAM selection (Ctrl/Shift toggles) and one delete for all selected.
        document.querySelector('#tsSteps button.ts-stage').click();
        check(document.body.dataset.particleStage==='select'&&getComputedStyle(document.querySelector('.comparison-pane')).display!=='none','Back to Select particles failed');
        const ids=particleRows().map(r=>r.candidate_id).slice(0,2);
        check(ids.length>0,'No particles to select: '+JSON.stringify(window.labParticleReplies));
        selectPoreFromDetails(ids[0],false,false);if(ids[1]!=null)selectPoreFromDetails(ids[1],true,false);
        await new Promise(r=>setTimeout(r,0)); // the strip count follows the selection on the next task
        check(getSelectedPores().length===ids.length&&$('particleRemove').textContent==='Remove selected ('+ids.length+')','Selection count missing in the strip');
        canvas.dispatchEvent(new KeyboardEvent('keydown',{key:'Delete',code:'Delete',bubbles:true,cancelable:true}));
        await idle();
        check(particleCalls.some(([r,d])=>r==='delete'&&Array.isArray(d.target_ids)&&d.target_ids.length===ids.length),'Delete did not remove all selected particles in one request');
        check($('particleModeHint').textContent.trim().split(/\s+/).length<=12&&!$('particleHint'),'Inspector guidance is longer than one short line');
        window.renderPoreDetails({dataset:'qa',revision:0,candidates:[{candidate_id:1,length_um:10,width_um:5,particle:true,particle_source:'auto'}],stats:{candidate_union_area_percent:0}});
        check($('poreDetailsTitle').textContent==='Particle Details'&&/Source/.test($('poreTable').querySelector('thead').textContent),'Details is not the Particle Details table');
        window.renderPoreDetails(await measurementSnapshot());
      }finally{api=realApi}
      showPanel('analysis');
      for(let n=0;n<200&&busy;n++)await new Promise(r=>setTimeout(r,100));
      check(!$('analysisPanel').classList.contains('hidden'),'Report panel did not open');
      check($('composedReportPreview').contentDocument?.body?.textContent.length>0,'Report preview is empty');
      check(!(window.labErrors||[]).length,'JavaScript errors: '+JSON.stringify(window.labErrors));
      check(!document.querySelector('[data-mode="tube"]')&&!$('labSample'),'Tube traces left in Report');
      await labChoose('labeling');
      lookChecks();
      check(document.querySelector('#tools [data-mode=select] svg'),'Icon rail missing');
      check(getComputedStyle(document.querySelector('[data-panel="analysis"]')).display==='none','Labeling exposes report step');
      check($('labAutoCommit').checked,'Labeling must default to immediate point edits');
      await prepareExisting(state.dataset);
      await $('runAnalysis').onclick();
      check(state.workspace_mode==='labeling'&&state.candidates.length>0,'Automatic labeling failed');
      const before=state.revision;
      const originalBase=base;
      await labPoint([90,100],1,false);
      check(state.revision>before&&!preview,'Immediate point edit did not commit: '+$('status').textContent);
      check(state.fast_instances&&state.instance_delta,'Incremental label response missing');
      check(base===originalBase,'Delta replaced the original image');
      const after=state.revision;
      await labPoint([45,55],0,true);
      check(state.revision>after,'Negative point refinement failed: '+$('status').textContent);
      const labelDataset=state.dataset,labelCount=state.candidates.length;
      await accept(await api('load',{dataset:labelDataset}));
      check(!state.instance_delta&&state.candidates.length===labelCount&&base,'Full label reload failed');
      const hotkey=code=>canvas.dispatchEvent(new KeyboardEvent('keydown',{code,key:code.slice(-1).toLowerCase(),bubbles:true,cancelable:true}));
      hotkey('KeyS');check(mode==='select','S did not select');
      const top=canvas.getBoundingClientRect().top;
      hotkey('KeyA');check(mode==='positive'&&$('labAutoCommit').checked,'A did not enable click add');
      check(Math.abs(canvas.getBoundingClientRect().top-top)<1,'Image jumps between Select and Add');
      hotkey('KeyD');check(mode==='delete','D did not enable click delete');
      check(Math.abs(canvas.getBoundingClientRect().top-top)<1,'Image jumps between Select and Delete');
      $('target').dispatchEvent(new KeyboardEvent('keydown',{code:'KeyS',key:'s',bubbles:true}));
      check(mode==='delete','Shortcut intercepted a form field');
      const picked=await api('object-at-point',{...payload(),point:[90,100]});
      check(picked.candidate_id!==null,'Deletion test object missing');
      const countBeforeDelete=state.candidates.length;
      await labDeleteAtPoint([90,100]);
      check(mode==='delete'&&state.candidates.length===countBeforeDelete-1,'Click delete failed or changed mode');
      await undoSavedEdit();
      check(state.candidates.length===countBeforeDelete,'Undo click delete failed');
      hotkey('KeyS');
      check(!(window.labErrors||[]).length,'JavaScript errors after labeling: '+JSON.stringify(window.labErrors));
      window.labQaResult={passed:true,english_default:true,report_preprocessing_hidden:true,mode_chooser:true,report_preview:true,no_tube:true,labeling_report_hidden:true,labeling_automatic_and_immediate_points:true,negative_point_refinement:true,particle_multiselect_delete:true,particle_auto_detect:true,particle_select_two_panes:true,particle_edit_lines:true,particle_line_delete:true,saved_dialog:true,particle_replies:window.labParticleReplies||[],javascript_errors:window.labErrors||[]};
    })().catch(e=>{window.labQaResult={passed:false,error:e.message,stack:e.stack,javascript_errors:window.labErrors||[]}});
    '''.replace('CONTENT',json.dumps(content))
    window.evaluate_js(script)
    deadline=time.monotonic()+180
    while time.monotonic()<deadline:
        result=window.evaluate_js('window.labQaResult')
        if result is not None:
            if not result.get('passed'): raise RuntimeError(json.dumps(result,ensure_ascii=False))
            return result
        time.sleep(.2)
    raise RuntimeError('Native UI smoke test timed out')
