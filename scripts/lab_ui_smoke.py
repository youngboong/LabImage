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
      // Sample control: native radios, Particles unless the user chose Tubes before.
      let storedSample=null;try{storedSample=localStorage.getItem('labimage.sample')}catch{}
      check($('labSample')?.querySelectorAll('input[type=radio][name=labSample]').length===2&&getComputedStyle($('labSample')).display!=='none','Sample control missing in Set up');
      check(labSample===(storedSample==='tubes'?'tubes':'particles')&&$('labSample').querySelector('input[value='+labSample+']').checked,'Sample does not default to Particles');
      check($('labSavedDialog') instanceof HTMLDialogElement,'Saved dialog element missing');
      labShowSaved(['C:/out/a(2).png','C:/out/a(3).png']);
      check($('labSavedDialog').open&&$('labSavedFolder').textContent==='C:/out'&&$('labSavedFiles').children.length===2,'Saved dialog does not list the folder and files');
      $('labSavedOk').click();check(!$('labSavedDialog').open,'Saved dialog OK does not close');
      labSampleSet('tubes',false); // the checks below are the Tubes workspace: empty, Add tool
      await $('runAnalysis').onclick();
      check(Boolean(state),'Report workflow did not open editor: '+$('status').textContent);
      check(state.candidates.length===0,'Report mode performed automatic analysis');
      check(mode==='positive','Point tool is not the default');
      await labPoint([90,100],1,false);
      check(Boolean(preview?.choices.length),'Point inference failed: '+$('status').textContent);
      check(state.candidates.length===0,'Report preview must wait for Apply');
      await $('apply').onclick();
      check(state.candidates.length===1,'Apply did not create the object: '+$('status').textContent);
      let measured=await measurementSnapshot();
      check(measured.candidates[0].length_um===null&&measured.candidates[0].width_um===null,'Unrequested automatic dimensions');
      $('manualStyle').value='polyline';$('manualStart').click();
      const clickPoint=p=>{
        const r=canvas.getBoundingClientRect();
        canvas.dispatchEvent(new PointerEvent('pointerdown',{bubbles:true,button:0,clientX:r.left+p[0]*r.width/canvas.width,clientY:r.top+p[1]*r.height/canvas.height}));
      };
      clickPoint([60,100]);clickPoint([90,70]);clickPoint([120,100]);
      check(manualPoints.length===3,'Curve pointer input failed');
      await $('manualSave').onclick();
      $('manualAxis').value='width';$('manualStyle').value='line';$('manualStart').click();
      clickPoint([90,80]);clickPoint([90,120]);
      await $('manualSave').onclick();
      measured=await measurementSnapshot();
      check(Math.abs(measured.candidates[0].length_um-84.8528)<.02,'Curve was measured as a chord');
      check(Math.abs(measured.candidates[0].width_um-40)<.02,'Manual W mismatch');
      await $('manualAutomatic').onclick();
      measured=await measurementSnapshot();
      check(measured.candidates[0].length_um===null,'Clear measurements failed');
      await accept(await api('undo',payload()));
      measured=await measurementSnapshot();
      check(measured.candidates[0].length_um>0,'Longitudinal measurement missing');
      check(measured.candidates[0].width_um>0,'Transverse measurement missing');
      await labRefreshOverlay();
      check(Boolean(labMeasurementImage),'Yellow measurement overlay missing');
      showPanel('analysis');
      for(let n=0;n<200&&busy;n++)await new Promise(r=>setTimeout(r,100));
      check(!$('analysisPanel').classList.contains('hidden'),'Report panel did not open');
      check($('composedReportPreview').contentDocument?.body?.textContent.length>0,'Report preview is empty');
      check(!(window.labErrors||[]).length,'JavaScript errors: '+JSON.stringify(window.labErrors));
      showPanel('editor');
      check(getComputedStyle(document.querySelector('[data-mode="polygon"]')).display!=='none','Polygon is hidden');
      document.querySelector('[data-mode="box"]').click();
      box=[175,50,275,165];draw();controls();
      document.querySelector('[data-mode="prompt-positive"]').click();
      check(Boolean(box),'Point + cleared the box');
      clickPoint([220,100]);
      document.querySelector('[data-mode="negative"]').click();clickPoint([177,53]);
      check(Boolean(box)&&labels.join(',')==='1,0','Box include/exclude prompts were lost');
      await $('predict').onclick();
      check(preview?.choices.length&&queuedRegions[0].input.labels.join(',')==='1,0','Box plus points preview failed');
      document.querySelector('[data-mode="prompt-positive"]').click();clickPoint([230,110]);
      check(queuedRegions[0].input.points.length===3,'Queued box point correction was lost');
      check(!$('updateRegionPreview').classList.contains('hidden'),'Update Preview missing for Point +');
      await $('updateRegionPreview').onclick();
      check(Boolean(preview?.choices.length),'Refined box preview missing');
      const boxCount=state.candidates.length;await $('apply').onclick();
      check(state.candidates.length===boxCount+1,'Box plus points Apply failed');
      document.querySelector('[data-mode="polygon"]').click();
      clickPoint([200,180]);clickPoint([230,180]);clickPoint([230,210]);
      await $('predict').onclick();
      check(Boolean(preview?.choices.length),'Polygon preview missing');
      const polygonCount=state.candidates.length;await $('apply').onclick();
      check(state.candidates.length===polygonCount+1,'Polygon Apply failed');
      document.querySelector('[data-mode="tube"]').click();
      check(mode==='tube','Tube tool did not open');
      tubeLineSet('auto');
      check(/Click one end/.test($('tsSteps').textContent),'Tube strip does not teach clicking both ends');
      check(!$('tubeHint')&&getComputedStyle($('tubeLine')).display!=='none'&&/Click/.test($('tubeLine').title),'Tubes panel must not carry a help paragraph; Line help belongs in the control tooltip');
      lookChecks();
      const tubeCalls=[],realApi=api;
      api=(route,data)=>{tubeCalls.push([route,data]);return realApi(route,data)};
      const drag=(type,p,button=0)=>{
        const r=canvas.getBoundingClientRect();
        canvas.dispatchEvent(new PointerEvent(type,{bubbles:true,cancelable:true,pointerId:9,button,buttons:type==='pointerup'?0:button===2?2:1,clientX:r.left+p[0]*r.width/canvas.width,clientY:r.top+p[1]*r.height/canvas.height}));
      };
      try{
        // A left drag traces nothing any more: only clicks place points.
        const before=tubeCalls.length;
        drag('pointerdown',[60,100]);for(const x of [75,90,105])drag('pointermove',[x,100]);drag('pointerup',[120,100]);
        check(tubeCalls.length===before&&!tubeCalls.some(([r,d])=>d?.stroke===true),'A left drag sent a stroke');
        tubeCancel();
        // Manual line: every click is a vertex; clicking the last point again saves it as drawn.
        tubeLineSet('manual');
        check(/Click along the tube/.test($('tsSteps').textContent),'Manual line steps missing');
        for(const p of [[60,100],[90,110],[120,100],[120,100]]){drag('pointerdown',p);drag('pointerup',p)}
        for(let n=0;n<300&&busy;n++)await new Promise(r=>setTimeout(r,100));
        check(tubeCalls.some(([r,d])=>r==='trace-tube'&&d.manual===true&&d.points.length===3),'Manual line was not sent as 3 clicked points');
        // Width only + Manual: a drag draws the first edge on release, a click on the other edge sends both.
        tubeKindSet('d');
        drag('pointerdown',[60,160]);drag('pointermove',[100,160]);drag('pointerup',[140,160]);
        check(tube.trace.length===2,'Edge drag did not draw the first line');
        drag('pointerdown',[100,175]);drag('pointerup',[100,175]);
        for(let n=0;n<300&&busy;n++)await new Promise(r=>setTimeout(r,100));
        check(tubeCalls.some(([r,d])=>r==='measure-tube'&&Array.isArray(d.edge)&&d.edge.length===2&&Array.isArray(d.point)),'Edge width was not sent');
        tubeKindSet('td');tubeLineSet('auto');
        const sent=tubeCalls.length;
        drag('pointerdown',[200,100],2);drag('pointerup',[200,100],2);
        check(tubeCalls.length===sent,'Right click without a drag sent a request');
        drag('pointerdown',[180,70],2);drag('pointermove',[260,140],2);drag('pointerup',[260,140],2);
        for(let n=0;n<300&&busy;n++)await new Promise(r=>setTimeout(r,100));
        check(tubeCalls.some(([r,d])=>r==='measure-tube'&&Array.isArray(d.box)&&d.box.length===4),'Right-drag box did not send a box');
      }finally{api=realApi}
      // Particles: Set up -> automatic Detect particles -> Select particles (two panes) -> Edit lines (one pane).
      // The synthetic image may make the backend answer 400, so mostly the requests are checked.
      const particleCalls=[],idle=async(n=300)=>{for(let i=0;i<n&&busy;i++)await new Promise(r=>setTimeout(r,100))};
      window.labParticleReplies=[]; // what the backend answered, for the smoke report
      api=(route,data)=>{particleCalls.push([route,data]);return realApi(route,data).then(r=>{window.labParticleReplies.push(route+': ok');return r},e=>{window.labParticleReplies.push(route+': '+e.message);throw e})};
      try{
        await prepareExisting(state.dataset);
        labSampleSet('particles',false);
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
      window.labQaResult={passed:true,english_default:true,report_preprocessing_hidden:true,manual_curve_input:true,object_path_endpoints:true,mode_chooser:true,point_default:true,report_no_automatic_masks:true,point_preview_apply:true,measurement_overlay:true,report_preview:true,labeling_report_hidden:true,labeling_automatic_and_immediate_points:true,negative_point_refinement:true,tube_manual_line_and_box:true,sample_control:true,particle_multiselect_delete:true,particle_auto_detect:true,particle_select_two_panes:true,particle_edit_lines:true,particle_line_delete:true,saved_dialog:true,particle_replies:window.labParticleReplies||[],javascript_errors:window.labErrors||[]};
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
