// LabImage's two workflows share immutable edits and the existing report composer.
let labMode=null,labMeasurementImage=null,labOverlayEpoch=0,labSession=null;
const labRunText=()=>labMode==='labeling'?'Run automatic labeling':'Detect particles';
document.title='LabImage';
document.querySelector('header h1').textContent='LabImage';
document.querySelector('.app-brand span').textContent='SAM 2.1';
document.querySelector('header').insertAdjacentHTML('beforeend','<span id="labModeBadge"></span><button id="labHomeButton" class="ghost sm" title="Switch workspace">Workspaces</button>');
document.querySelector('header .app-brand').after(document.querySelector('nav.steps')); // one 48 px chrome row; tab order brand, steps, Workspaces
const labHome=document.createElement('section');labHome.id='labHome';
labHome.innerHTML=`<div class="lab-home-inner"><h1>LabImage</h1><p class="lab-home-lead">Choose a workspace. Both run on this computer with the SAM 2.1 Small model.</p><div class="lab-mode-cards"><button id="labChooseLabel"><svg class="home-art" viewBox="0 0 132 72" aria-hidden="true" focusable="false"><rect class="well" width="132" height="72" rx="5"/><path class="obj" d="M14 38c0-11 8-18 17-17s14 9 12 17-11 13-18 12-11-4-11-12z"/><path class="obj" d="M56 22c7-6 18-4 21 3s0 16-8 18-17-2-17-10 2-8 4-11z"/><path class="obj" d="M86 46c1-9 10-14 17-11s8 13 2 17-14 5-17 1-2-4-2-7z"/><text class="id" x="26" y="40">1</text><text class="id" x="63" y="35">2</text><text class="id" x="96" y="50">3</text></svg><strong>Labeling</strong><span>Segment every object automatically, correct it with points, and export instance masks.</span><small>16-bit PNG masks, NumPy arrays and metadata</small><b>Start labeling</b></button><button id="labChooseReport"><svg class="home-art" viewBox="0 0 132 72" aria-hidden="true" focusable="false"><rect class="well" width="132" height="72" rx="5"/><path class="grain" d="M18 41c-1-9 12-16 34-19s52-5 59 3-4 17-28 21-48 6-58 3-7-4-7-8z"/><path class="m" d="M18 41L112 29"/><path class="m" d="M61 23L65 50"/><circle class="end" cx="18" cy="41" r="2.2"/><circle class="end" cx="112" cy="29" r="2.2"/><circle class="end" cx="61" cy="23" r="2"/><circle class="end" cx="65" cy="50" r="2"/><rect class="chipbox" x="98" y="54" width="20" height="12" rx="2"/><text x="101.5" y="63">L1</text></svg><strong>Report</strong><span>Segment objects with prompts, measure lengths and widths, and build a report.</span><small>Measurement figure, CSV, and PDF, HWPX and Word reports</small><b>Start a report</b></button></div><p class="lab-home-foot">Runs offline with the official SAM 2.1 Small model. No fine-tuning.</p></div>`;
document.body.append(labHome);
$('regionSettings').before(Object.assign(document.createElement('p'),{className:'hint',textContent:'Measure in pixels, or calibrate against a known distance.'}));
$('regionSettings').insertAdjacentHTML('beforebegin','<label class="lab-calibration-toggle"><input type="checkbox" id="labCalibrated"> Calibrate in micrometres (µm)</label>');
const labControlPanel=document.createElement('section');labControlPanel.className='panel lab-controls';
labControlPanel.innerHTML=`<h2>Segment</h2><p class="hint">Click inside an object to segment it. Shift-click refines; right-click excludes.</p><label><input id="labAutoCommit" type="checkbox"> Apply point edits immediately</label><button id="labNewObject" class="wide" title="Clear the prompts and start a new object (Esc)">New object</button><p id="labPromptStatus" class="hint">Start with a point. Use Box when points are not enough.</p><details><summary>More tools</summary><p class="hint">Ellipse and cut tools, for hard cases.</p><button id="labAdvancedTools" class="sm" aria-pressed="false">Show ellipse and cut</button></details>`;
document.querySelector('#editorPanel aside').prepend(labControlPanel);
const labRuntimeNotice=document.createElement('p');
labRuntimeNotice.className='notice hidden';labRuntimeNotice.setAttribute('role','status');
labControlPanel.prepend(labRuntimeNotice);
const labMeasurements=document.createElement('section');labMeasurements.className='panel lab-report-only';labMeasurements.id='labMeasurementSettings';
labMeasurements.innerHTML=`<h2>Figure appearance</h2><label><input id="labShowMeasurements" type="checkbox" checked> Show measurement paths and labels</label><label><input id="labShowLength" type="checkbox" checked> L, longitudinal path</label><label><input id="labShowWidth" type="checkbox" checked> W, transverse path</label><label class="field">Label size (image px)<input id="labFontSize" type="number" min="8" max="64" value="16"></label><p class="hint">Measure each axis with two endpoints. Values stay blank until measured. Area and perimeter are in Object details.</p>`;
labControlPanel.after(labMeasurements);
$('refreshMeasurements').closest('section').classList.add('lab-report-only');
document.querySelector('[data-mode="positive"]').textContent='Add (A)';
document.querySelector('[data-mode="select"]').textContent='Select (S)';
document.querySelector('[data-mode="negative"]').textContent='Point −';
document.querySelector('[data-mode="box"]').textContent='Box';
const tools=$('tools');
for(const m of ['positive','negative','box']) tools.prepend(document.querySelector(`[data-mode="${m}"]`));
// Reinsert in the desired order after moving out of upstream tool groups.
for(const m of ['box','negative','positive']) tools.prepend(document.querySelector(`[data-mode="${m}"]`));
const labIncludeTool=document.createElement('button');
labIncludeTool.dataset.mode='prompt-positive';labIncludeTool.textContent='Point +';
labIncludeTool.title='Add an include point to a box or region preview.';
tools.insertBefore(labIncludeTool,document.querySelector('[data-mode="negative"]'));
tools.append(document.querySelector('[data-mode="polygon"]'));
labIncludeTool.onclick=()=>{
  if(busy)return;
  // Use the underlying point tool without Add's new-object reset.
  document.querySelector('[data-mode="positive"]').onclick();
  mode='prompt-positive';
  document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b===labIncludeTool));
  $('toolHint').textContent='Include point: keep the box and refine its boundary.';
  window.renderRegionQueue?.();
};
const labDeleteTool=document.createElement('button');
labDeleteTool.dataset.mode='delete';labDeleteTool.textContent='Delete (D)';
labDeleteTool.title='Click an object to delete it. Ctrl+Z restores it.';
tools.insertBefore(labDeleteTool,document.querySelector('[data-mode="negative"]'));
labDeleteTool.onclick=()=>{
  if(busy)return;
  document.querySelector('[data-mode="select"]').click();
  mode='delete';labResetPrompt();canvas.style.cursor='crosshair';
  document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b===labDeleteTool));
  $('predict').classList.add('hidden');$('toolHint').textContent='Click an object to delete. Ctrl+Z to undo.';
  window.updateToolLayout?.();
};
document.querySelector('[data-mode="positive"]').addEventListener('click',()=>{
  labResetPrompt();$('labAutoCommit').checked=true;
});
$('labAdvancedTools').onclick=()=>{const on=document.body.classList.toggle('lab-advanced');$('labAdvancedTools').setAttribute('aria-pressed',String(on));$('labAdvancedTools').textContent=on?'Hide ellipse and cut':'Show ellipse and cut'};

function labSetMode(value){
  labMode=value;document.body.dataset.labMode=value;
  $('labModeBadge').textContent=value==='labeling'?'Labeling':'Report';
  $('labAutoCommit').checked=value==='labeling';
  $('runAnalysis').textContent=labRunText();
  $('saveEditorImages').title=value==='labeling'?'Export instance masks to a folder':'Export the measurement figure and CSV to a folder';
}
async function labChoose(value){
  labSetMode(value);labHome.classList.add('hidden');showPanel('load');
  await refreshLists();
}
$('labChooseLabel').onclick=()=>labChoose('labeling');$('labChooseReport').onclick=()=>labChoose('report');
$('labHomeButton').onclick=()=>{if(busy)return;labHome.classList.remove('hidden')};

const labApi=api;
api=async function(route,data){
  if(route==='analyze') data={...data,config:{...data.config,workspace_mode:labMode||'labeling',calibrated:$('labCalibrated').checked}};
  return labApi(route,data);
};
const labValidate=validateAnalysisInput;
validateAnalysisInput=function(){
  if($('labCalibrated').checked)return labValidate();
  if(!setupProject)throw new Error('Choose an image first.');
  for(const id of ['analysisBottom','minArea'])if(!$(id).value||!$(id).checkValidity())throw new Error('Check the image region and minimum area.');
};
const labCalibration=updateCalibration;
updateCalibration=function(){
  if($('labCalibrated').checked)return labCalibration();
  $('calibrationInfo').textContent='Pixel units. No physical calibration.';
  $('minAreaInfo').textContent='Minimum area '+$('minArea').value+' px²';
};
function labCalibrationVisibility(){
  const enabled=$('labCalibrated').checked;
  for(const element of [$('scaleUm').closest('.two-fields'),$('scaleFactorField'),$('scaleConfirmed').parentElement,$('measureScale')])element.classList.toggle('hidden',!enabled);
  updateCalibration();
}
$('labCalibrated').onchange=labCalibrationVisibility;
// Particles: the user's own tick on "Confirm calibration" goes straight on to analysis and detection (a scale read from the
// microscope file is pre-confirmed without an event, so it waits for the Detect particles button).
$('scaleConfirmed').addEventListener('change',e=>{if(e.isTrusted&&$('scaleConfirmed').checked&&labMode==='report'&&!busy&&!window.activeStopOperation)$('runAnalysis').onclick()});
const labRun=$('runAnalysis').onclick;
$('runAnalysis').onclick=async()=>{
  const before=state?state.dataset+':'+state.revision:null;
  await labRun();
  // Particles: a new, empty report workspace gets Detect particles right away.
  if(labMode==='report')for(let i=0;i<50&&(busy||!state||$('editorPanel').classList.contains('hidden'));i++)await new Promise(r=>setTimeout(r,100)); // the workspace may still be opening
  if(labMode==='report'&&state&&!busy&&!state.candidates.length&&state.dataset+':'+state.revision!==before&&!$('editorPanel').classList.contains('hidden')){particleEnter('select');await particleDetect()}
};
const labShowProject=showProject;
showProject=async function(project){
  await labShowProject(project);
  if(project.footer_detection?.detected){
    const bottom=project.footer_detection.bottom;
    $('imageDetails').textContent+=`. Bottom information strip excluded (${project.height-bottom} px).`;
    $('analysisBottom').max=$('bottomSlider').max=bottom;
  }
  $('labCalibrated').checked=project.config.calibrated===true;
  labCalibrationVisibility();
  const meta=project.scale_metadata;
  if(meta&&project.config.calibrated!==true){ // an earlier run without calibration must not hide the file's own scale
    const px=meta.length_pixels||100;$('scalePixels').value=px;$('scaleUm').value=meta.label_um||+(px*meta.um_per_pixel).toFixed(4);
    $('labCalibrated').checked=true;labCalibrationVisibility();
  }
  if(project.scale_metadata&&$('scaleUm').value&&$('scalePixels').value){ // scale read from the microscope file: filled in and confirmed, still editable
    $('scaleConfirmed').checked=true;updateCalibration();jobMessage('Scale read from the image file. Ready.');
    $('imageDetails').textContent+=` Scale read from the image file: ${project.scale_metadata.um_per_pixel.toFixed(4)} µm/px.`;
  }
  $('runAnalysis').textContent=labRunText();
};
const labPanel=showPanel;
showPanel=function(name){if(name==='analysis'&&labMode==='labeling')return;return labPanel(name)};
const labControls=controls;
controls=function(){
  labControls();
  if(labMode==='labeling')document.querySelector('[data-panel="analysis"]').disabled=true;
  document.body.classList.toggle('is-busy',busy);$('viewport').setAttribute('aria-busy',String(busy));
  if(labMode==='report')labReportControls();
};
const labLayer=window.drawPoreLayer;
window.drawPoreLayer=function(context){
  if(labMode==='report'&&mode!=='particle'&&labMeasurementImage&&$('labShowMeasurements').checked&&$('showOverlay').checked){context.drawImage(labMeasurementImage,0,0);return} // Particles: outlines and IDs; Edit lines draws its own lines
  return labLayer(context);
};
async function labRefreshOverlay(){
  const epoch=++labOverlayEpoch;
  if(!state||labMode!=='report'){labMeasurementImage=null;draw();return}
  const key=state.dataset+':'+state.revision;
  try{
    const result=await api('measurement-overlay',{...payload(),show_length:$('labShowLength').checked,show_width:$('labShowWidth').checked,show_ids:$('showPoreLabels').checked,font_size:Math.max(8,Math.min(64,Number($('labFontSize').value)||16)),opacity:Number($('poreOpacity').value)});
    const overlay=await image(result.image);
    if(epoch!==labOverlayEpoch||!state||state.dataset+':'+state.revision!==key)return;
    labMeasurementImage=overlay;draw();
  }catch(error){if(epoch===labOverlayEpoch)setStatus(error.message,true)}
}
for(const id of ['labShowLength','labShowWidth','labFontSize','showPoreLabels','poreOpacity'])$(id).addEventListener('change',labRefreshOverlay);
$('labShowMeasurements').onchange=draw;
const labAccepted=window.onEditorAccepted;
let labToolDataset=null;
window.onEditorAccepted=function(data){
  if(!state||labSession?.dataset!==data.dataset)labSession=null;
  labMeasurementImage=null;labSetMode(data.workspace_mode||labMode||'report');
  labAccepted?.(data);labRefreshOverlay();
  // Another analysis opened: particles always start at Select particles (the last one may have been left in Edit lines).
  if(labToolDataset!==data.dataset){if(labMode==='report')particleEnter('select');else if(mode==='select')document.querySelector('[data-mode="positive"]').onclick()}
  labToolDataset=data.dataset;
};
const labSelectImage=selectImage;
selectImage=selection=>{if(selection?.dataset)labToolDataset=null;return labSelectImage(selection)}; // reopening the same analysis also starts at Select particles
// Do not reset the user's auto-commit choice on every revision.
const labSetModeOriginal=labSetMode;
labSetMode=function(value){const changed=labMode!==value,auto=$('labAutoCommit').checked;labSetModeOriginal(value);if(!changed)$('labAutoCommit').checked=auto};

function labResetPrompt(){
  labSession=null;clear();$('target').value='';
  $('labPromptStatus').textContent='Click inside a new object. Shift-click refines.';
}
$('labNewObject').onclick=labResetPrompt;
const labPrompts=n=>n+(n===1?' prompt':' prompts');
async function labPoint(point,label,refine){
  if(busy||!state)return;
  let session=labSession;
  const selected=window.getSelectedPores?.()||[];
  if(!refine||!session||session.dataset!==state.dataset){
    const target=$('target').value||((label===0&&selected.length===1)?selected[0]:null);
    session={dataset:state.dataset,points:[],labels:[],target_id:target?Number(target):null};
  }
  if(label===0&&!session.points.length&&session.target_id===null){setStatus('Add a positive point or select an object first.',true);return}
  session.points.push(point);session.labels.push(label);labSession=session;
  points=structuredClone(session.points);labels=[...session.labels];box=null;shape=null;polygon=[];
  draw();
  await work('Segmenting with SAM 2.1…',async()=>{
    const response=await api('quick-segment',{...payload(),points:session.points,labels:session.labels,target_id:session.target_id,auto_apply:$('labAutoCommit').checked});
    if(response.applied){
      session.target_id=response.applied_target_id;
      if(response.effective_points){session.points=response.effective_points;session.labels=response.effective_labels}
      await accept(response);session.token=null;labSession=session;
      $('labPromptStatus').textContent='Object #'+session.target_id+', '+labPrompts(session.points.length);
      setStatus('Applied. Shift-click to refine, right-click to exclude, Ctrl+Z to undo.');
      return;
    }
    session.target_id=response.target_id;session.token=response.token;
    if(response.effective_points){session.points=response.effective_points;session.labels=response.effective_labels}
    $('target').value=response.target_id===null?'':String(response.target_id);
    await presentPreview(response);
    if($('labAutoCommit').checked){
      const previousIds=new Set(state.candidates.map(c=>c.candidate_id));
      const result=await api('apply',{...payload(),token:response.token,choice:0,target_id:response.target_id});
      if(session.target_id===null)session.target_id=result.candidates.find(c=>!previousIds.has(c.candidate_id))?.candidate_id??null;
      await accept(result);
      session.token=null;labSession=session;
      setStatus('Applied. Shift-click to refine, right-click to exclude, Ctrl+Z to undo.');
    }else setStatus('Preview ready. Refine with points, then press Enter or Add object.');
    $('labPromptStatus').textContent=(session.target_id?'Object #'+session.target_id+', ':'New object, ')+labPrompts(session.points.length);
  });
}
window.handleLabPointer=function(event){
  if(mode==='delete'){
    canvas.focus();labDeleteAtPoint(eventPoint(event));return true;
  }
  if(!['positive','prompt-positive','negative'].includes(mode))return false;
  if(mode!=='positive'&&window.addRegionPrompt?.(eventPoint(event),mode==='negative'?0:1))return true;
  labPoint(eventPoint(event),mode==='negative'?0:1,mode==='negative'||event.shiftKey||Boolean(preview));return true;
};
async function labDeleteAtPoint(point){
  if(busy||!state)return;
  await work('Deleting object...',async()=>{
    const request=payload();
    const picked=await api('object-at-point',{...request,point});
    if(picked.candidate_id===null){setStatus('No object at this point.');return}
    await accept(await api('delete',{...request,target_ids:[picked.candidate_id]}));
    setStatus('Deleted object #'+picked.candidate_id+'. Ctrl+Z to undo.');
  });
}
document.addEventListener('keydown',event=>{
  if(event.ctrlKey||event.metaKey||event.altKey||event.repeat||event.isComposing||busy||drag||!state)return;
  if($('editorPanel').classList.contains('hidden')||!labHome.classList.contains('hidden')||document.querySelector('dialog[open]'))return;
  if(event.target.closest?.('input,textarea,select')||event.target.isContentEditable)return;
  const tool={KeyS:'select',KeyA:'positive',KeyD:'delete',KeyP:'particle'}[event.code];
  if(!tool||(tool==='particle'&&labMode!=='report'))return; // Particle is a Report tool
  event.preventDefault();document.querySelector(`[data-mode="${tool}"]`).click();canvas.focus();
});
canvas.addEventListener('contextmenu',event=>{
  event.preventDefault();
  if(busy||!state||!['positive','prompt-positive','negative','box'].includes(mode))return;
  if(window.addRegionPrompt?.(eventPoint(event),0))return;
  if(mode!=='box')labPoint(eventPoint(event),0,true);
});
document.addEventListener('keydown',event=>{
  if(event.target.closest?.('input,textarea,select')||busy||!state)return;
  if(event.key==='Enter'&&preview&&!$('apply').disabled){event.preventDefault();$('apply').click()}
  if(event.key==='Escape'){labResetPrompt()}
});
const labApply=$('apply').onclick;
$('apply').onclick=async()=>{
  const session=labSession,previousIds=new Set(state?.candidates.map(c=>c.candidate_id)||[]);
  await labApply();
  if(session&&state&&!preview){
    if(session.target_id===null)session.target_id=state.candidates.find(c=>!previousIds.has(c.candidate_id))?.candidate_id??null;
    session.token=null;labSession=session;
  }
};
$('clear').addEventListener('click',()=>{labSession=null});
$('saveEditorImages').onclick=()=>work('Saving images…',async()=>{
  if(!state)return;
  if(labMode==='report'){
    // Particles: <name>(1) minimum Feret widths and <name>(2) lengths, value-only labels, plus two CSVs.
    const body={...payload(),font_size:Number($('labFontSize').value)};
    let saved=await api('save-labels',body);
    if(saved.need_folder){const picked=await api('choose-export-folder',{});if(!picked.directory){setStatus('Save cancelled.');return}body.directory=picked.directory;saved=await api('save-labels',body)}
    if(saved.saved){setStatus('Saved '+saved.saved.join(', '));labShowSaved(saved.saved);return}
  }
  const picked=await api('choose-export-folder',{});if(!picked.directory){setStatus('Export cancelled.');return}
  const result=await api('export-images',{...payload(),directory:picked.directory,opacity:Number($('poreOpacity').value),labels:$('showPoreLabels').checked,show_length:$('labShowLength').checked,show_width:$('labShowWidth').checked,font_size:Number($('labFontSize').value)});
  setStatus((labMode==='labeling'?'Instance masks saved to ':'Measurement figure and CSV saved to ')+result.exported_folder);
});
// "Saved" dialog after Save images (Particles): native modal <dialog>, so focus stays inside and Esc closes it.
// No "Open folder" button: the backend has no API that reveals a folder.
const labSavedDialog=document.createElement('dialog');labSavedDialog.id='labSavedDialog';labSavedDialog.setAttribute('aria-labelledby','labSavedTitle');
labSavedDialog.innerHTML=`<div class="dialog-head"><h2 id="labSavedTitle">${window.labIcon('check','saved-icon')}Saved</h2></div><p class="hint">Check the figures and tables in this folder:</p><p id="labSavedFolder" class="saved-folder"></p><ul id="labSavedFiles" class="saved-files"></ul><div class="row"><button id="labSavedOk" class="primary" type="button">OK</button></div>`;
document.body.append(labSavedDialog);
$('labSavedOk').onclick=()=>labSavedDialog.close();
// Enter closes it too. The OK button cannot take focus when the dialog opens (buttons are disabled while saving), so the key is caught on the document.
document.addEventListener('keydown',event=>{if(event.key==='Enter'&&labSavedDialog.open){event.preventDefault();event.stopImmediatePropagation();labSavedDialog.close()}},true);
// Batch: every image of a folder is calibrated from its file, detected and saved beside the original (name(1), name(2), CSVs).
// Images that already have (1) and (2) are skipped; otherwise an image is analysed again. Each result can be reviewed later from Open analysis.
$('newImagePane').insertAdjacentHTML('beforeend','<div class="row lab-report-only"><button id="labBatch" type="button" title="Detect particles in every image of a folder and save name(1) minimum Feret width, name(2) length and CSV files beside each image. Images that already have both are skipped.">Process a folder…</button></div>');
// Update: the latest GitHub release may carry a small patch; the app downloads it, closes, swaps the files and starts again.
$('newImagePane').insertAdjacentHTML('beforeend','<div class="row lab-update"><button id="labUpdate" type="button">Check for updates</button><span id="labUpdateState" class="hint" role="status"></span></div>');
$('labUpdate').onclick=async()=>{
  const say=(text,bad)=>{$('labUpdateState').textContent=text;$('labUpdateState').classList.toggle('error',!!bad)};
  $('labUpdate').disabled=true;say('Checking…');
  try{
    const found=await api('update-check',{});
    if(!found.update){say(`LabImage ${found.current} is up to date.`);return}
    if(!found.patch){say(`Version ${found.latest} needs a full install: ${found.page}`);return}
    if(!confirm(`Update LabImage ${found.current} to ${found.latest}? (${Math.round(found.patch.size/1e6)} MB) LabImage closes and starts again.`)){say(`Version ${found.latest} is available.`);return}
    say('Downloading. LabImage will restart…');
    await api('update-install',{});
  }catch(error){say(error.message,true)}
  finally{$('labUpdate').disabled=false}
};
const labBatchDialog=document.createElement('dialog');labBatchDialog.id='labBatchDialog';labBatchDialog.setAttribute('aria-labelledby','labBatchTitle');
labBatchDialog.innerHTML='<div class="dialog-head"><h2 id="labBatchTitle">Process a folder</h2></div><p id="labBatchFolder" class="saved-folder"></p><p id="labBatchState" class="hint" role="status"></p><form id="labBatchSetup" class="row"><label class="field">Correction factor<input id="labBatchFactor" type="number" min="0.01" max="100" step="any" required title="Every length is multiplied by this factor, areas by its square. Detection is not affected."></label><button id="labBatchStart" class="primary" type="submit">Start</button></form><progress id="labBatchBar" max="1" value="0" aria-label="Batch progress"></progress><div class="results-wrap"><table class="results"><caption class="sr-only">Batch results</caption><thead><tr><th scope="col">Image</th><th scope="col">Result</th></tr></thead><tbody id="labBatchRows"></tbody></table></div><div class="row"><button id="labBatchStop" type="button">Stop</button><button id="labBatchClose" class="primary" type="button">Close</button></div>';
document.body.append(labBatchDialog);
let labBatchTimer=0;
function labBatchShow(b){
  const text=r=>r.status==='saved'?`${r.particles} particle${r.particles===1?'':'s'} saved, ${r.excluded} left out${r.unit==='px'?' (px: no scale in file)':''}`:r.status==='skipped'?'Skipped: '+r.note:r.status==='no particles'?'No measurable particle':'Failed: '+(r.note||'');
  $('labBatchFolder').textContent=b.folder||'';$('labBatchBar').max=b.total||1;$('labBatchBar').value=b.done;
  const n=k=>b.results.filter(r=>r.status===k).length;
  $('labBatchState').textContent=b.running?`${b.done} / ${b.total}${b.current?' · '+b.current:''} · correction ×${b.scale_factor}`:`Done: ${n('saved')} saved, ${n('skipped')} skipped, ${n('no particles')} without particles, ${n('failed')} failed.`;
  $('labBatchRows').replaceChildren(...b.results.map(r=>{const tr=el('tr');tr.append(el('td','',r.name),el('td',r.status==='failed'?'error':'',text(r)));return tr}));
  $('labBatchStop').hidden=!b.running;$('labBatchClose').disabled=b.running;
  $('labBatchSetup').hidden=true;$('labBatchBar').hidden=false;labBatchDialog.querySelector('.results-wrap').hidden=false;
}
async function labBatchPoll(){
  clearTimeout(labBatchTimer);
  let b;try{b=await api('batch-status',{})}catch(error){$('labBatchState').textContent=error.message;$('labBatchClose').disabled=false;return}
  labBatchShow(b);
  if(b.running)labBatchTimer=setTimeout(labBatchPoll,1000);else refreshLists?.();
}
$('labBatch').onclick=async()=>{
  try{
    const picked=await api('choose-export-folder',{});if(!picked.directory)return;
    const last=await api('batch-status',{});
    // ask for the correction factor first (the last one used is the default), then start
    labBatchDirectory=picked.directory;
    $('labBatchFolder').textContent=picked.directory;$('labBatchState').textContent='Lengths are multiplied by the correction factor. Use 1 for none.';
    $('labBatchRows').replaceChildren();$('labBatchBar').hidden=true;labBatchDialog.querySelector('.results-wrap').hidden=true;$('labBatchStop').hidden=true;$('labBatchClose').disabled=false;
    $('labBatchFactor').value=last.last_scale_factor??1;$('labBatchSetup').hidden=false;
    if(!labBatchDialog.open)labBatchDialog.showModal();
    $('labBatchFactor').focus();$('labBatchFactor').select();
  }catch(error){setStatus(error.message,true);jobMessage?.(error.message,true)}
};
let labBatchDirectory='';
$('labBatchSetup').onsubmit=async event=>{
  event.preventDefault();
  $('labBatchStart').disabled=true;
  try{
    labBatchShow(await api('batch-particles',{directory:labBatchDirectory,scale_factor:Number($('labBatchFactor').value)}));
    labBatchTimer=setTimeout(labBatchPoll,1000);
  }catch(error){$('labBatchState').textContent=error.message}
  finally{$('labBatchStart').disabled=false}
};
$('labBatchStop').onclick=async()=>{$('labBatchStop').disabled=true;try{await api('batch-stop',{})}finally{$('labBatchStop').disabled=false}};
$('labBatchClose').onclick=()=>labBatchDialog.close();
labBatchDialog.addEventListener('cancel',event=>{if($('labBatchClose').disabled)event.preventDefault()}); // Esc does not hide a running batch
function labShowSaved(paths){
  const split=p=>{const i=Math.max(p.lastIndexOf('/'),p.lastIndexOf('\\'));return [p.slice(0,i),p.slice(i+1)]};
  $('labSavedFolder').textContent=split(paths[0])[0];
  $('labSavedFiles').replaceChildren(...paths.map(p=>Object.assign(document.createElement('li'),{textContent:split(p)[1]})));
  if(!labSavedDialog.open)labSavedDialog.showModal();
  $('labSavedOk').focus();
}
$('resetCriteria').onclick=()=>{
  $('minContrast').value=0;$('minArea').value=100;$('pointDensity').value=16;
  $('normalizeEnabled').checked=false;$('backgroundStrength').value=0;$('blurMethod').value='none';$('blurStrength').value=0;invalidatePreprocessing();
};
$('backgroundHelp').textContent='Use the original image by default. Review boundaries when applying processing.';
// Pore-specific contrast heuristics and automated box proposals are not exposed.
$('minContrast').closest('label').classList.add('hidden');
$('openFeedback').classList.add('hidden');
labCalibrationVisibility();
document.querySelector('.app-brand span').textContent='SAM 2.1';

// Report setup contains calibration only; processing belongs to labeling.
$('normalizeEnabled').closest('section').classList.add('lab-label-only');
$('preprocessingImage').closest('section').classList.add('lab-label-only');
$('regionSettings').classList.add('lab-label-only');
const labModeLayout=labSetMode;
labSetMode=function(value){
  labModeLayout(value);
  if(window.labRailReady)labRailSample(); // defined further down; this also runs during start-up
  const steps=value==='report'?[['Load image','Load'],['Set scale','Scale'],['Measure particles','Measure'],['Build report','Report']]:[['Load image','Load'],['Set up','Setup'],['Label and refine','Label'],['Build report','Report']];
  document.querySelectorAll('.steps [data-panel]').forEach((b,i)=>{b.querySelector('.sl-long').textContent=steps[i][0];b.querySelector('.sl-short').textContent=steps[i][1]});
  document.querySelector('#setupPanel .workspace-intro h2').textContent=value==='report'?'Image and scale':'Labeling setup';
  if(value==='report'){
    $('normalizeEnabled').checked=false;$('backgroundStrength').value=0;
    $('blurMethod').value='none';$('blurStrength').value=0;
  }
};
const manualPanel=document.createElement('section');
manualPanel.className='panel lab-report-only';manualPanel.id='manualPanel';
manualPanel.innerHTML=`<h2>Endpoint measurements</h2>
<p class="hint">LabImage places the center point automatically. Mark both ends of L and W; each path runs through that center inside the object. Labels are drawn outside the object.</p>
<label class="field">Object<select id="manualObject"></select></label>
<button id="manualAutomatic" class="wide">Clear saved measurements</button>
<div class="two-fields"><label class="field">Axis<select id="manualAxis"><option value="length">L, longitudinal</option><option value="width">W, transverse</option></select></label>
<label class="field">Path<select id="manualStyle"><option value="line">Through center (2 points)</option><option value="freehand">Draw a curve</option><option value="polyline">Click curve points</option></select></label></div>
<button id="manualStart" class="wide">Set endpoints</button>
<p id="manualHint" class="hint">Mark two endpoints for the selected axis, then Save path. Draw a curve if the traced route needs correction.</p>
<div class="row"><button id="manualSave" class="primary" disabled>Save path</button><button id="manualBack" disabled>Undo point</button><button id="manualCancel">Cancel</button></div>
<p id="manualValue" class="manual-value">No path yet</p>`;
labMeasurements.before(manualPanel);
let manualActive=false,manualDragging=false,manualPoints=[];
function manualUpdate(){
  const d=manualPoints.slice(1).reduce((v,p,i)=>v+Math.hypot(p[0]-manualPoints[i][0],p[1]-manualPoints[i][1]),0);
  $('manualValue').textContent=!manualActive?'No path yet':manualPoints.length>1?($('manualStyle').value==='line'?'Ready to trace through the object':`${d.toFixed(2)} px along the drawn path, ${manualPoints.length} points`):'Mark the first point';
  $('manualSave').disabled=busy||manualPoints.length<2||d===0;
  $('manualBack').disabled=!manualPoints.length;
  draw();
}
function manualStop(){
  manualActive=false;manualDragging=false;manualPoints=[];
  $('manualStart').classList.remove('active');manualUpdate();
}
$('manualStart').onclick=()=>{
  if(busy||!state||!$('manualObject').value){setStatus('Segment an object first.',true);return}
  clear();manualActive=true;manualPoints=[];$('manualStart').classList.add('active');
  $('manualHint').textContent=$('manualStyle').value==='freehand'?'Press and drag from start to end. Save path when finished.':$('manualStyle').value==='polyline'?'Click successive points along the curve, then Save path.':'Click two points on the selected object. Save path connects both endpoints through the yellow center inside its mask. Review the yellow curve or draw your own.';
  manualUpdate();
};
$('manualCancel').onclick=manualStop;
$('manualAutomatic').onclick=()=>work('Clearing measurements…',async()=>{
  if(!state||!$('manualObject').value)return;
  const data=await api('manual-measurement',{...payload(),object_id:Number($('manualObject').value),reset_automatic:true});
  manualStop();await accept(data);renderMeasurements(await measurementSnapshot());
  setStatus('Measurements cleared. Choose endpoints to measure again.');
});
$('manualBack').onclick=()=>{manualPoints.pop();manualUpdate()};
for(const id of ['manualObject','manualAxis','manualStyle'])$(id).onchange=manualStop;
$('manualSave').onclick=()=>work('Saving measurement…',async()=>{
  const data=await api('manual-measurement',{...payload(),object_id:Number($('manualObject').value),axis:$('manualAxis').value,points:manualPoints,method:$('manualStyle').value==='line'?'object_path':'drawn_path'});
  manualStop();await accept(data);renderMeasurements(await measurementSnapshot());
  setStatus('Measurement saved. Ctrl+Z undoes the last saved change.');
});
canvas.addEventListener('pointerdown',e=>{
  if(!manualActive||labMode!=='report')return;
  e.preventDefault();e.stopImmediatePropagation();
  if(busy||e.button!==0)return;
  const p=eventPoint(e),style=$('manualStyle').value;
  if(style==='freehand'){manualPoints=[p];manualDragging=true;canvas.setPointerCapture(e.pointerId)}
  else if(style==='line'){if(manualPoints.length===2)manualPoints=[];manualPoints.push(p)}
  else manualPoints.push(p);
  manualUpdate();
},true);
canvas.addEventListener('pointermove',e=>{
  if(!manualDragging)return;e.stopImmediatePropagation();
  const p=eventPoint(e),last=manualPoints.at(-1);
  if(Math.hypot(p[0]-last[0],p[1]-last[1])>=.7&&manualPoints.length<9999){manualPoints.push(p);manualUpdate()}
},true);
canvas.addEventListener('pointerup',e=>{
  if(!manualDragging)return;e.stopImmediatePropagation();
  manualPoints.push(eventPoint(e));manualDragging=false;manualUpdate();
},true);
canvas.addEventListener('pointercancel',()=>{if(manualDragging)manualStop()},true);
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&manualActive)manualStop()});
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',manualStop));
window.drawManualMeasurement=c=>{
  if(!manualActive||!manualPoints.length)return;
  const yellow=getComputedStyle(document.body).getPropertyValue('--measure').trim()||'#ffff00';
  c.save();c.strokeStyle=yellow;c.fillStyle=yellow;c.lineWidth=2;c.setLineDash([]);
  if($('manualStyle').value!=='line'){c.beginPath();manualPoints.forEach((p,i)=>i?c.lineTo(...p):c.moveTo(...p));c.stroke()}
  for(const p of [manualPoints[0],manualPoints.at(-1)]){c.beginPath();c.arc(...p,4,0,Math.PI*2);c.fill()}
  c.restore();
};
const manualAccepted=window.onEditorAccepted;
window.onEditorAccepted=function(data){
  manualStop();manualAccepted?.(data);
  document.querySelector('.app-brand span').textContent=data.inference_device==='intel-gpu'?'SAM 2.1 on Intel GPU':'SAM 2.1 on CPU';
  labRuntimeNotice.textContent=data.runtime_notice||'';
  labRuntimeNotice.classList.toggle('hidden',!data.runtime_notice);
  const previous=$('manualObject').value;
  $('manualObject').replaceChildren(...data.candidates.map(c=>new Option('Object #'+c.candidate_id,String(c.candidate_id))));
  if([...$('manualObject').options].some(o=>o.value===previous))$('manualObject').value=previous;
};

// ---- Report workspace UI: tool rail, hint strip, collapsible panels, particle results.
const ICON=window.LAB_ICON; // ui/icons.js
const TOOL_UI={
  select:{name:'Select',key:'S',tip:'Select objects. Ctrl-click adds or removes one.',text:'Click to select. Ctrl-click adds or removes.',keys:[['Ctrl+click','multi-select'],['Del','delete selected']]},
  particle:{name:'Particle',key:'P',tip:'Measure flat particles: detect them all, click one, or draw its length and width lines.'},
  positive:{name:'Add',key:'A',tip:'Add an object: click inside it and SAM segments it.',text:'Click inside an object to segment it with SAM. Shift-click refines; right-click excludes.',keys:[['Shift+click','refine'],['Right-click','exclude'],['Ctrl+Z','undo']]},
  'prompt-positive':{name:'Point +',tip:'Add an include point to a box or region preview.',text:'Add an include point to refine the current box or preview.',keys:[['Enter','apply preview']]},
  negative:{name:'Point −',tip:'Add an exclude point.',text:'Click outside the object to exclude that area.',keys:[['Right-click','same as Point −']]},
  box:{name:'Box',tip:'Drag a box to guide segmentation.',text:'Drag a box around the object, then press Preview.',keys:[['Point +/−','refine the box']]},
  polygon:{name:'Polygon',tip:'Click vertices to outline an object.',text:'Click vertices around the object, then press Preview polygon.',keys:[]},
  ellipse:{name:'Ellipse',tip:'Drag an ellipse to guide segmentation.',text:'Drag an ellipse around the object, then press Preview.',keys:[]},
  cut:{name:'Cut',tip:'Drag a cut through an object.',text:'Drag across an object to split it, then press Apply cuts.',keys:[]},
  delete:{name:'Delete',key:'D',tip:'Click an object to delete it. Ctrl+Z restores it.',text:'Click an object to delete it. Ctrl+Z restores it.',keys:[['Ctrl+Z','undo']]},
  back:{name:'Undo',tip:'Undo the last trace point, drawing input or saved edit (Ctrl+Z).'},
  clear:{name:'Clear',tip:'Clear the current drawing and cancel any trace.'}
};
// Drag gestures (particle Draw): less travel than GESTURE_PX screen px is a click.
const GESTURE_PX=5;
let gesture=null,resultFresh=null,resultKey='',resultTimer=0,labDataset=null; // gesture: {button, id, x, y, shift, moved, points: image px}
// Particle tool (docs/particle-design.md, docs/ui-design.md "Particle workflow"): stage Select particles (raw image left, selected particles right;
// a click adds or removes a whole particle), then stage Edit lines (one image; Select a line and delete it, or Draw a length or width line).
const PARTICLE_STAGES={select:'Select particles',lines:'Edit lines'};
const PARTICLE_WARN={cut_off:'this particle touches the image border',overlapped:'this particle touches another particle',overlapped_shape:'its outline is not convex, so it may be overlapped or folded',standing:'this particle may be standing on its edge',not_particle:'this may be background, not a particle',small:'this particle is very small'};
const PARTICLE_SRC={auto:'Auto',click:'Click',manual:'Manual line'};
let particle={trace:[],cursor:null,sent:null},particleAxis='length',particleStage='select',particleLineTool='select',lineSel=null; // lineSel: {id, axis|null} in Edit lines
const svg=(path,cls='')=>`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${path}</svg>`;
function el(tag,cls,text){const e=document.createElement(tag);if(cls)e.className=cls;if(text!==undefined)e.textContent=text;return e}

// Tool rail: one icon rail for both workspaces (icon + name + shortcut). Particle stays Report-only through its class.
const labSeparators=['sep-a','sep-b','sep-c'].map(cls=>Object.assign(document.createElement('span'),{className:'tool-sep '+cls,role:'separator'}));
// Keep DOM order equal to the visual order so Tab follows the rail.
function labRailOrder(){
  const items=[...tools.querySelectorAll('[data-mode],#back,#clear')];
  labSeparators.forEach(x=>x.remove());
  const pick=k=>labSeparators.find(x=>x.classList.contains(k))??items.find(b=>(b.dataset.mode||b.id)===k);
  ['select','particle','sep-a','positive','prompt-positive','negative','box','polygon','ellipse','cut','sep-b','delete','sep-c','back','clear'].map(pick).filter(Boolean).forEach(n=>tools.append(n));
}
function labRailRender(){
  labRailOrder();
  for(const b of document.querySelectorAll('#tools [data-mode],#back,#clear')){
    const key=b.dataset.mode||b.id,meta=TOOL_UI[key];if(!meta)continue;
    b.innerHTML=svg(ICON[key],'ti')+`<span class="tl">${meta.name}</span>`+(meta.key?`<kbd class="tk" aria-hidden="true">${meta.key}</kbd>`:'');
    b.title=meta.tip+(meta.key?` (${meta.key})`:'');
    b.setAttribute('aria-label',meta.name+(meta.key?` (${meta.key})`:''));
    if(meta.key)b.setAttribute('aria-keyshortcuts',meta.key);
  }
}
const labSetModeUI=labSetMode;
labSetMode=function(value){
  labSetModeUI(value);
  $('regionPanel').querySelector('h2').textContent=value==='report'?'Region preview':'Segment';
  labStrip();
};

// Contextual hint strip above the image (both workspaces; fixed 40 px so the canvas never moves).
const toolStrip=document.createElement('section');
toolStrip.id='toolStrip';toolStrip.setAttribute('aria-label','Current tool');
toolStrip.innerHTML=`<div class="ts-name">${svg('')}<span id="tsName"></span></div><p class="ts-text" id="tsText"></p><ol class="ts-steps" id="tsSteps" aria-label="Particle stages"></ol>
<button id="particleDetect" class="sm lab-report-only" type="button" title="Find and measure every flat, whole particle again (about 10 s). Ctrl+Z removes the added ones.">Detect particles</button><fieldset id="particleEdit" class="segmented lab-report-only"><legend>Tool</legend><label><input type="radio" name="particleEdit" value="select"><span>Select</span></label><label><input type="radio" name="particleEdit" value="draw"><span>Draw</span></label></fieldset><fieldset id="particleAxis" class="segmented lab-report-only"><legend>Line</legend><label><input type="radio" name="particleAxis" value="length"><span><svg class="pl-key" viewBox="0 0 20 10" aria-hidden="true" focusable="false"><path class="h" d="M3 5h14M3 1.5v7M17 1.5v7"/><path class="c len" d="M3 5h14M3 1.5v7M17 1.5v7"/></svg>Length</span></label><label><input type="radio" name="particleAxis" value="width"><span><svg class="pl-key" viewBox="0 0 20 10" aria-hidden="true" focusable="false"><path class="h" d="M4 5h12"/><path class="c wid" d="M4 5h12"/><circle class="d wid" cx="4" cy="5" r="2.6"/><circle class="d wid" cx="16" cy="5" r="2.6"/></svg>Width</span></label></fieldset><fieldset id="particleWidthMode" class="segmented lab-report-only" title="Which automatic width lines are shown and edited. Save image writes name(1) with the minimum width either way. Lines you drew by hand are the same in both."><legend>Width</legend><label title="Minimum Feret: the narrowest gap between two parallel lines that hold the particle."><input type="radio" name="particleWidthMode" value="min" checked><span>Minimum</span></label><label title="The earlier width: Feret diameter perpendicular to the length line."><input type="radio" name="particleWidthMode" value="perpendicular"><span>Perpendicular</span></label></fieldset><button id="particleDetails" class="sm lab-report-only" type="button" title="Open the Details window: table and distributions">Details</button><button id="particleRemove" class="danger sm lab-report-only" type="button" aria-keyshortcuts="Delete">Remove selected</button><button id="particleNext" class="primary sm lab-report-only" type="button">Next: edit lines</button><p class="ts-keys" id="tsKeys"></p>`;
document.querySelector('.document-toolbar').after(toolStrip);
document.querySelector('.document-toolbar').before(tools); // DOM order = Tab order: rail, document bar, strip, canvas, inspector
function labStrip(){
  if(!labMode)return;
  const meta=TOOL_UI[mode]||TOOL_UI.select,isParticle=mode==='particle';
  const toolChanged=document.body.dataset.tool!==mode;
  const layoutChanged=toolChanged||(isParticle&&document.body.dataset.particleStage!==particleStage);
  document.body.dataset.tool=mode;document.body.dataset.particleStage=particleStage;document.body.dataset.particleEdit=particleLineTool;
  const [capL,capR]=document.querySelectorAll('.comparison-pane h2');
  capL.textContent=isParticle?'Raw image':'Original';capR.textContent=isParticle?(particleStage==='select'?'Selected particles: click to add or remove':'Length and width lines'):'Segmentation';
  if(layoutChanged)window.resizeComparison?.(); // Edit lines hides the Original pane; refit the image to the pane that is left
  toolStrip.querySelector('.ts-name svg').innerHTML=ICON[mode]||ICON.select;
  $('tsName').textContent=meta.name;
  $('tsText').textContent=$('tsText').title=isParticle?particleHint():meta.text||'';$('tsText').hidden=isParticle;$('tsSteps').hidden=!isParticle;
  $('openPoreDetails').lastChild.textContent=isParticle?'Particle details':'Open object details'; // PoreSAM: Details opens from the list panel
  if(isParticle){ // the two stages; the other stage is a button, so Back and Next are one click
    $('tsSteps').classList.add('idle');
    $('tsSteps').replaceChildren(...Object.entries(PARTICLE_STAGES).map(([s,label],i)=>{
      const now=s===particleStage,li=el('li',now?'now':i?'':'done'),t=now?li:li.appendChild(el('button','ts-stage'));li.dataset.step=i+1;
      if(now)li.setAttribute('aria-current','step');else{t.type='button';t.setAttribute('aria-label',(i?'Go to ':'Back to ')+label);t.onclick=()=>particleStageSet(s);t.disabled=busy||!state}
      t.append(el('b','',String(i+1)),el('span','ts-label',label));return li;
    }));
  }
  $('tsKeys').replaceChildren();
  for(const [k,t] of (isParticle?particleKeys():meta.keys)||[]){const s=el('span');s.append(el('kbd','',k),t);$('tsKeys').append(s)}
  document.querySelectorAll('[data-mode]').forEach(b=>b.setAttribute('aria-pressed',String(b.classList.contains('active'))));
}
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',labStrip));

// Collapsible side panels (report-only panels; labeling never shows them).
function labCollapsible(panel,collapsed){
  const h=panel.querySelector(':scope>h2');if(!h)return;
  panel.classList.add('panel-collapsible');
  const b=el('button','ph-toggle',h.textContent);b.type='button';h.replaceChildren(b); // real button inside the heading keeps the heading in the outline
  const set=c=>{panel.classList.toggle('collapsed',c);b.setAttribute('aria-expanded',String(!c))};
  b.onclick=()=>set(!panel.classList.contains('collapsed'));
  set(collapsed);
}
labCollapsible(labMeasurements,true);labCollapsible(manualPanel,false);

// Results panel: every measured particle.
const resultPanel=document.createElement('section');
resultPanel.className='panel lab-report-only';resultPanel.id='resultPanel';
resultPanel.innerHTML=`<div class="panel-head"><h2>Particles <span id="resultCount" class="chip-count" data-n="0"></span></h2><button id="resultUndo" class="sm" type="button" title="Undo the last point or saved edit (Ctrl+Z)">Undo</button></div>
<p id="resultStatus" class="hint" role="status"></p>
<p id="particleModeHint" class="hint particle-only"></p>
<button id="resultCalib" class="sm" type="button" hidden title="Lengths are in pixels until the scale is set">${svg(ICON.warning)}Lengths are in pixels. Set the scale</button>
<div id="particleEmpty" class="empty particle-only">${svg(ICON.particle)}<p>No particles yet.</p><button id="particleEmptyDetect" class="primary" type="button" title="Find and measure every flat, whole particle (about 10 s)">Detect particles</button></div>
<div id="resultTable" class="results-wrap" hidden><table class="results"><caption class="sr-only">Measured objects</caption><thead><tr><th scope="col">ID</th><th scope="col" id="resultLenHead">Length</th><th scope="col" id="resultWidHead">Width</th><th scope="col"><span class="sr-only">Delete</span></th></tr></thead><tbody id="resultRows"></tbody><tfoot id="resultFoot"></tfoot></table></div>`;
manualPanel.before(resultPanel);
const particleTool=document.createElement('button');
particleTool.id='particleTool';particleTool.dataset.mode='particle';particleTool.className='lab-report-only';
tools.insertBefore(particleTool,document.querySelector('[data-mode="negative"]'));
$('resultCalib').onclick=()=>document.querySelector('.steps [data-panel=setup]')?.click();
$('resultUndo').onclick=()=>labUndo();
function labUndo(){
  if(busy)return;
  if(particle.trace.length){particleCancel();return}
  if(inputHistory.length)return undoInput();
  if(state?.can_undo)return undoSavedEdit();
}
const labBack=$('back').onclick;
$('back').onclick=()=>labMode==='report'?labUndo():labBack();

// Report-mode control states that controls() cannot know (it only toggles by busy).
function labReportControls(){
  particleTool.disabled=$('particleDetect').disabled=$('particleEmptyDetect').disabled=$('particleNext').disabled=$('particleDetails').disabled=busy||!state;
  $('particleRemove').disabled=busy||!state||!(window.getSelectedPores?.().length);
  $('tsSteps').querySelectorAll('button').forEach(b=>b.disabled=busy||!state);
  $('particleEdit').querySelectorAll('input').forEach(r=>r.disabled=busy||!state);
  $('particleAxis').querySelectorAll('input').forEach(r=>r.disabled=busy||!state);
  $('particleWidthMode').querySelectorAll('input').forEach(r=>r.disabled=busy||!state);
  $('resultUndo').disabled=busy||!(particle.trace.length||inputHistory.length||state?.can_undo);
  $('back').disabled=$('resultUndo').disabled;
}

// Shift while drawing a line: the new end snaps to the nearest 45° (horizontal, vertical or diagonal) from the previous point.
function snapAngle(from,to,shift){
  if(!shift||!from||!to)return to;
  const step=Math.PI/4,a=Math.round(Math.atan2(to[1]-from[1],to[0]-from[0])/step)*step,c=Math.cos(a),s=Math.sin(a);
  const d=(to[0]-from[0])*c+(to[1]-from[1])*s;
  return [from[0]+d*c,from[1]+d*s];
}
function gestureStart(event,point){
  gesture={button:event.button,id:event.pointerId,x:event.clientX,y:event.clientY,shift:event.shiftKey,moved:false,points:[point]};
  try{canvas.setPointerCapture(event.pointerId)}catch{/* synthetic events have no active pointer */}
}
function gestureEnd(){
  const g=gesture;gesture=null;
  try{if(g&&canvas.hasPointerCapture(g.id))canvas.releasePointerCapture(g.id)}catch{/* already released */}
  labStrip();draw();
  return g;
}
canvas.addEventListener('pointermove',event=>{
  const g=gesture;if(!g||event.pointerId!==g.id)return;
  if(!g.moved){
    if(Math.hypot(event.clientX-g.x,event.clientY-g.y)<GESTURE_PX)return;
    g.moved=true;
    labStrip();
  }
  g.points[1]=g.button===0?snapAngle(g.points[0],eventPoint(event),event.shiftKey):eventPoint(event);
  if(!drawFrame)drawFrame=requestAnimationFrame(()=>{drawFrame=0;draw()});
});
canvas.addEventListener('pointerup',event=>{
  if(!gesture||event.pointerId!==gesture.id)return;
  const g=gestureEnd(),p=g.button===0?snapAngle(g.points[0],eventPoint(event),event.shiftKey):eventPoint(event);
  if(particleActive()&&!busy&&state)particleRelease(g,p);
});
for(const type of ['pointercancel','lostpointercapture'])canvas.addEventListener(type,event=>{if(gesture&&event.pointerId===gesture.id)gestureEnd()}); // never leave a drag stuck
window.addEventListener('blur',()=>{if(gesture)gestureEnd()});
document.addEventListener('keydown',event=>{
  if(event.key!=='Escape'||!gesture)return;
  event.preventDefault();event.stopImmediatePropagation();gestureEnd();
},true);
document.querySelectorAll('[data-mode]').forEach(b=>b.addEventListener('click',()=>{if(gesture)gestureEnd()}));
let drawFrame=0;

// Results list (#id matches the labels drawn on the figure).
function resultRender(data){
  const unit=data.measurement_unit||'µm',rows=data.candidates.filter(r=>r.length_um!=null||r.width_um!=null).sort((a,b)=>b.candidate_id-a.candidate_id);
  $('resultCount').textContent=rows.length||'';$('resultCount').dataset.n=rows.length;
  $('particleEmpty').hidden=rows.length>0;$('resultTable').hidden=!rows.length;$('resultCalib').hidden=unit!=='px';
  $('resultLenHead').textContent=`Length (${unit})`;$('resultWidHead').textContent=`Width (${unit})`;
  const cell=value=>{const td=el('td');td.append(el('span',value==null?'none':'val',value==null?'—':value.toFixed(2)));if(value==null)td.setAttribute('aria-label','Not measured');return td};
  const body=rows.map(r=>{
    const tr=el('tr'),id=r.candidate_id;
    tr.dataset.id=id;tr.tabIndex=0;if(id===resultFresh||resultFresh?.has?.(id))tr.className='fresh';
    const first=el('td');first.append(el('span','id-plain','#'+id),el('span','src',r.particle?PARTICLE_SRC[r.particle_source??r.particle.source]||'Particle':'Manual path'));
    const remove=el('button','icon-btn');remove.type='button';remove.title='Delete #'+id+' (Ctrl+Z restores it)';remove.setAttribute('aria-label',(r.particle?'Delete particle ':'Delete object ')+id);remove.innerHTML=svg(ICON.delete);
    remove.onclick=e=>{e.stopPropagation();resultDelete(id)};
    const last=el('td');last.append(remove);
    tr.append(first,cell(r.length_um),cell(r.width_um),last);
    const pick=()=>window.selectPoreFromDetails?.(id);
    tr.onclick=pick;tr.onkeydown=e=>{if(e.target===tr&&(e.key==='Enter'||e.key===' ')){e.preventDefault();pick()}};
    return tr;
  });
  resultFresh=null;
  $('resultRows').replaceChildren(...body);
  const mean=key=>{
    const v=rows.map(r=>r[key]).filter(x=>x!=null),n=v.length;if(!n)return '—';
    const m=v.reduce((a,b)=>a+b,0)/n;
    if(n<2)return m.toFixed(2);
    const td=el('td');td.append(el('span','val',m.toFixed(2)),el('span','sd','± '+Math.sqrt(v.reduce((a,x)=>a+(x-m)**2,0)/(n-1)).toFixed(2)));return td; // SD on its own line keeps the readout inside the inspector
  };
  const footCell=v=>v instanceof Element?v:el('td','',v);
  const count=key=>rows.filter(r=>r[key]!=null).length;
  const nl=count('length_um'),nw=count('width_um');
  const foot=el('tr');foot.append(el('td','',`Mean ± SD (n = ${nl===nw||!nw?nl:!nl?nw:nl+' L, '+nw+' W'})`),footCell(mean('length_um')),footCell(mean('width_um')),el('td'));
  $('resultFoot').replaceChildren(...(rows.length>1?[foot]:[]));
  resultSyncSelection();
}
function resultSyncSelection(){
  const selected=new Set(window.getSelectedPores?.()||[]);
  $('resultRows').querySelectorAll('tr').forEach(tr=>{const on=selected.has(Number(tr.dataset.id));tr.classList.toggle('selected',on);tr.setAttribute('aria-selected',String(on))});
}
new MutationObserver(resultSyncSelection).observe($('selectedPoreCount'),{childList:true,characterData:true,subtree:true});
function resultDelete(id){
  return work('Deleting #'+id+'…',async()=>{await accept(await api('delete',{...payload(),target_ids:[id]}));setStatus('Deleted #'+id+'. Ctrl+Z to undo.')});
}
const labRenderMeasurements=renderMeasurements;
renderMeasurements=function(data){
  labRenderMeasurements(data);
  if(labMode==='report'){resultKey=data.dataset+':'+data.revision;resultRender(data)}
};
// Undo, delete and manual edits change the list without calling renderMeasurements; refresh it quietly.
function resultSchedule(){
  clearTimeout(resultTimer);
  resultTimer=setTimeout(async()=>{
    if(labMode!=='report'||!state||resultKey===state.dataset+':'+state.revision)return;
    try{renderMeasurements(await measurementSnapshot())}catch{/* superseded by a newer revision */}
  },250);
}
const resultAccepted=window.onEditorAccepted;
window.onEditorAccepted=function(data){
  if(data.dataset!==labDataset){labDataset=data.dataset;particle.trace=[];particle.cursor=null;resultKey=''}
  resultAccepted?.(data);
  labStrip();resultSchedule();
};

// Mirror errors into the Particles panel (the status bar already shows them).
const labStatusBase=setStatus;
setStatus=function(text,error=false){
  const hit=error&&labMode==='report'&&/^This particle is already measured as #(\d+)\.?$/.exec(text),hitId=hit&&hit[1];
  if(hit){text+=' It is now selected. Delete it to measure again.';setTimeout(()=>{window.selectPoreFromDetails?.(Number(hitId));document.querySelector(`#resultRows tr[data-id="${hitId}"]`)?.scrollIntoView({block:'nearest'})})} // after work() clears busy
  $('status').title='';labStatusBase(text,error); // a caller may add details as a tooltip after this
  if(error&&mode==='particle'&&labMode==='report'){$('resultStatus').textContent=text;$('resultStatus').classList.add('error')}
  else if($('resultStatus').classList.contains('error')){$('resultStatus').textContent='';$('resultStatus').classList.remove('error')}
};
// ---- Particle tool: stage Select particles (raw image left, selected particles right) and stage Edit lines (one image; Select | Draw, Length | Width).
// Edit lines draws every row's length_line / width_line itself, in two on-screen colours (--particle-length, --particle-width); saved figures stay yellow.
const particleActive=()=>mode==='particle'&&labMode==='report';
const particleK=()=>Math.max(.5,canvas.width/(canvas.getBoundingClientRect().width||canvas.width)); // image px per screen px
const particleColor=axis=>getComputedStyle(document.body).getPropertyValue(axis==='length'?'--particle-length':'--particle-width').trim()||(axis==='length'?'#ff9f1a':'#4cc3ff');
const particleLineOk=l=>Array.isArray(l)&&l.length===2&&l.every(p=>Array.isArray(p)&&p.length===2&&p.every(Number.isFinite)); // rows without lines are skipped quietly
// Rows of the latest measurement snapshot (same image; a newer revision replaces them within one request).
const particleRows=()=>summarySnapshot&&state&&summarySnapshot.dataset===state.dataset?summarySnapshot.candidates:[];
const particleSelected=()=>{const ids=window.getSelectedPores?.()||[];return ids.length===1?ids[0]:null};
// One short line of guidance in the inspector; the strip carries the controls and keys (PoreSAM: few words, the image does the work).
function particleHint(){
  if(particleStage==='select')return 'Click to select, Shift-click to add more, Delete to remove.';
  if(particleLineTool==='select')return 'Click a line, then Delete removes that line.';
  return particle.trace.length?`Click the other end of the ${particleAxis} line.`:`Click both ends of the ${particleAxis} line.`;
}
function particleKeys(){
  if(particleStage==='select')return [['Click','select or add'],['Shift+click','multi-select'],['Del','remove'],['Esc','clear']];
  return particleLineTool==='select'?[['Click','select a line'],['Del','delete it'],['Esc','clear']]:[['Click twice','draw'],['Drag','draw'],['Esc','cancel']];
}
// Selection uses the app's object selection (object-list.js, as in PoreSAM): Shift- or Ctrl-click toggles, Delete removes all selected in one undo.
// lineSel narrows it to one line of the one selected particle (Edit lines).
function particleSelUpdate(){
  const id=particleSelected(),n=(window.getSelectedPores?.()||[]).length;
  if(lineSel&&(lineSel.id!==id||lineSel.axis&&!particleLineOk(particleRows().find(r=>r.candidate_id===id)?.[lineSel.axis+'_line'])))lineSel=null;
  const b=$('particleRemove'),axis=lineSel?.axis;
  b.innerHTML=axis?'Delete line':`Remove<span class="rm-long"> selected</span> (${n})`;b.setAttribute('aria-label',axis?`Delete the ${axis} line of #${id}`:`Remove ${n} selected particles`);
  b.title=axis?`Delete only the ${axis} line of #${id} (Delete). Draw it again with Draw.`:'Remove the selected particles (Delete). Ctrl+Z restores them.';
  b.hidden=particleStage==='lines'&&!n;b.disabled=busy||!state||!n;
}
function particleUpdate(){
  $('particleModeHint').textContent=$('toolHint').textContent=particleHint();
  $('particleNext').textContent=particleStage==='select'?'Next: edit lines':'Build report';
  canvas.style.cursor=particleActive()&&(particleStage==='select'||particleLineTool==='select')?'default':'crosshair';
  particleSelUpdate();labStrip();draw();
}
function particleCancel(){particle.trace=[];particle.cursor=null;particleUpdate()}
function particleStageSet(stage){
  particleStage=stage;lineSel=null;
  window.labFillScale=stage==='lines'?.3:1; // Edit lines: the particle surface stays visible under the lines
  particleCancel(); // labStrip refits the panes when the stage changes
}
function particleEditSet(value){
  particleLineTool=value;
  $('particleEdit').querySelectorAll('input').forEach(r=>{r.checked=r.value===value});
  particleCancel();
}
function particleAxisSet(value){
  particleAxis=value;
  $('particleAxis').querySelectorAll('input').forEach(r=>{r.checked=r.value===value});
  particleCancel();
}
$('particleEdit').addEventListener('change',e=>{if(e.target.name==='particleEdit')particleEditSet(e.target.value)}); // native radios: arrow keys work without JS
$('particleAxis').addEventListener('change',e=>{if(e.target.name==='particleAxis')particleAxisSet(e.target.value)});
// Width: Minimum (default) or Perpendicular to the length. One request changes every automatic width line; Ctrl+Z undoes it.
let particleWidthMode='min';
const particleWidthShow=()=>$('particleWidthMode').querySelectorAll('input').forEach(r=>{r.checked=r.value===particleWidthMode});
$('particleWidthMode').addEventListener('change',e=>{
  if(e.target.name!=='particleWidthMode')return;
  const mode=e.target.value;
  work('Changing the width lines…',async()=>{
    try{await particleSave(await api('particle-width-mode',{...payload(),mode}));setStatus(mode==='min'?'Width: minimum Feret. Ctrl+Z to undo.':'Width: perpendicular to the length. Ctrl+Z to undo.')}
    finally{particleWidthShow()} // a refused change puts the radio back
  });
});
// Also called while busy (a new analysis opening), when the rail buttons are disabled.
function particleEnter(stage=particleStage){
  const select=document.querySelector('[data-mode="select"]');if(select.disabled)select.onclick();else select.click();
  mode='particle';labResetPrompt();manualStop();particle.trace=[];particle.cursor=null;
  document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b===particleTool));
  $('predict').classList.add('hidden');
  window.updateToolLayout?.();particleStageSet(stage);
}
particleTool.onclick=()=>{if(!busy)particleEnter()};
// Report: the rail keeps Select, Particle, Delete, Undo and Clear. Select and Delete work inside the particle stages
// instead of opening the generic segmentation view (where a line or a label cannot be clicked).
const particleFlow=()=>labMode==='report';
function labRailSample(){
  for(const b of tools.querySelectorAll('[data-mode]'))if(!['select','particle','delete'].includes(b.dataset.mode))b.hidden=particleFlow();
  window.labFillScale=particleFlow()&&mode==='particle'&&particleStage==='lines'?.3:1;
}
tools.addEventListener('click',event=>{
  const b=event.target.closest?.('[data-mode]');
  if(!b||!particleFlow()||busy||!state||!['select','delete'].includes(b.dataset.mode))return;
  event.preventDefault();event.stopImmediatePropagation();
  if(mode!=='particle')particleEnter();
  if(b.dataset.mode==='select'){if(particleStage==='lines')particleEditSet('select');return}
  if((window.getSelectedPores?.()||[]).length)particleDeleteSelected();
  else{if(particleStage==='lines')particleEditSet('select');setStatus(particleStage==='lines'?'Click a line, its label or a particle, then press Delete.':'Click a particle (Shift-click for more), then press Delete.')}
},true);
document.querySelectorAll('[data-mode]').forEach(b=>{if(b!==particleTool)b.addEventListener('click',()=>{lineSel=null;if(particle.trace.length)particleCancel()})});
// Hook for the next stage: a separate Edit-lines module (window.particleEdit.open) takes over when present; else the built-in Edit lines below.
$('particleNext').onclick=()=>{if(busy||!state)return;if(particleStage!=='select')return document.querySelector('.steps [data-panel=analysis]').click();if(window.particleEdit?.open)window.particleEdit.open();else particleStageSet('lines')};
$('particleDetails').onclick=()=>$('openPoreDetails').click();
function particleSummary(p){const f=v=>v.toFixed(2)+' '+p.unit;return [p.length!=null&&'L '+f(p.length),p.width!=null&&'W '+f(p.width)].filter(Boolean).join(', ')}
async function particleSave(result,fresh){
  if(fresh!=null)resultFresh=fresh;
  await accept(result);renderMeasurements(await measurementSnapshot());
}
// Short status; the reasons go in the status bar's tooltip.
async function particleDetect(){
  await work('Detecting particles… (about 10 s)',async()=>{
    const result=await api('detect-particles',payload()),ids=result.object_ids||[],e=result.excluded||{};
    await particleSave(result,new Set(ids));
    const out=[['cut off',e.cut_off],['overlapped',(e.overlapped||0)+(e.overlapped_shape||0)],['not particles',e.not_particle],['standing',e.standing],['too small',e.small]].filter(([,n])=>n>0);
    const left=out.reduce((s,[,n])=>s+n,0);
    setStatus(`Added ${ids.length}.${left?` Left out ${left}.`:''}`);
    $('status').title=(left?`Left out: ${out.map(([w,n])=>n+' '+w).join(', ')}. `:'')+'Ctrl+Z removes all added.';
  });
}
$('particleDetect').onclick=()=>particleDetect();
$('particleEmptyDetect').onclick=()=>particleDetect();
// Select particles: a click on a particle selects it (Shift or Ctrl toggles); a plain click where there is none measures the particle there.
// The clicked point stays on the image (dimmed) while the request runs.
async function particleAdd(point){
  particle.sent=[point];draw();
  try{await work('Measuring particle…',async()=>{
    const result=await api('measure-particle',{...payload(),point}),id=result.object_id;
    await particleSave(result,id);
    setStatus(`Added #${id}.${result.warning?` Check: ${PARTICLE_WARN[result.warning]||result.warning}.`:''}`);
    if(result.particle)$('status').title=particleSummary(result.particle);
  })}finally{particle.sent=null;draw()}
}
function particleRemoveSelected(){
  const ids=window.getSelectedPores?.()||[];if(!ids.length||busy)return;
  return work('Removing…',async()=>{await particleSave(await api('delete',{...payload(),target_ids:ids}));setStatus(`Removed ${ids.length}. Ctrl+Z to undo.`)}); // one request, one undo
}
// Edit lines, Draw: object_id only when one particle (or one of its lines) is selected; then this axis is replaced.
async function particleLine(points){
  const axis=particleAxis,id=particleSelected();particle.trace=[];particle.cursor=null;particle.sent=points;particleUpdate();
  try{await work(`Saving the ${axis} line…`,async()=>{
    const result=await api('particle-line',{...payload(),axis,points,...(id!=null?{object_id:id}:{})}),rid=result.object_id;
    await particleSave(result,rid);
    setStatus(`${result.created?'Added':'Saved '+axis+' line of'} #${rid}.`);
    if(result.particle)$('status').title=particleSummary(result.particle);
  })}finally{particle.sent=null;draw()}
}
// Edit lines, Select: the nearest drawn line within 6 screen px, else the particle under the click (object selection), else nothing.
function particleLineAt(point){
  const k=particleK();let best=null;
  for(const b of particleLabels)if(point[0]>=b.x0&&point[0]<=b.x1&&point[1]>=b.y0&&point[1]<=b.y1)return {id:b.id,axis:b.axis,d:0}; // its value label counts as the line
  for(const r of particleRows())for(const axis of ['length','width']){
    const l=r[axis+'_line'];if(!particleLineOk(l))continue;
    const [a,b]=l,dx=b[0]-a[0],dy=b[1]-a[1],t=Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy||1)));
    const d=Math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy);
    if(d<=6*k&&(!best||d<best.d))best={id:r.candidate_id,axis,d};
  }
  return best;
}
function particleSelectLine(hit){
  const current=window.getSelectedPores?.()||[];
  if(current.length!==1||current[0]!==hit.id)window.selectPoreFromDetails?.(hit.id,false,false);
  lineSel={id:hit.id,axis:hit.axis};particleSelUpdate();draw();
}
function particleDeleteSelected(){
  const id=particleSelected(),axis=lineSel?.id===id?lineSel?.axis:null;
  if(!axis)return particleRemoveSelected();
  if(busy)return;
  return work(`Deleting the ${axis} line…`,async()=>{
    const result=await api('particle-line',{...payload(),object_id:id,axis,points:null});
    await particleSave(result);
    lineSel=null;particleAxisSet(axis); // ready to draw it again
    setStatus(result.removed?`Deleted #${id}: it had no other line. Ctrl+Z to undo.`:`Deleted ${axis} line of #${id}.`);
  });
}
$('particleRemove').onclick=()=>particleDeleteSelected();
const particlePointer=window.handleLabPointer;
window.handleLabPointer=function(event){
  if(!particleActive())return particlePointer(event);
  canvas.focus();
  const point=eventPoint(event),first=particle.trace[0],toggle=event.shiftKey||event.ctrlKey||event.metaKey;
  if(particleStage==='select'){lineSel=null;window.pickPoreAtPoint?.(point,toggle,(window.getSelectedPores?.()||[]).length?null:particleAdd);return true} // with a selection, a click on nothing clears it first (PoreSAM)
  if(particleLineTool==='select'){const hit=!toggle&&particleLineAt(point);if(hit)particleSelectLine(hit);else{lineSel=null;window.pickPoreAtPoint?.(point,toggle)}return true}
  if(!first){gestureStart(event,point);return true} // press-drag-release draws the line; a click sets the first end
  const end=snapAngle(first,point,event.shiftKey);
  if(Math.hypot(end[0]-first[0],end[1]-first[1])>=1)particleLine([first,end]);
  return true;
};
function particleRelease(g,p){
  if(g?.button!==0)return; // a right drag does nothing in this tool
  if(g.moved)particleLine([g.points[0],p]);else{particle.trace=[g.points[0]];particleUpdate()}
}
canvas.addEventListener('pointermove',event=>{
  if(!particleActive()||!particle.trace.length||busy)return;
  particle.cursor=snapAngle(particle.trace[0],eventPoint(event),event.shiftKey);
  if(!drawFrame)drawFrame=requestAnimationFrame(()=>{drawFrame=0;draw()});
});
canvas.addEventListener('pointerleave',()=>{if(particle.cursor){particle.cursor=null;draw()}});
document.addEventListener('keydown',event=>{
  if(!particleActive()||!particle.trace.length||busy||!state||event.altKey||event.isComposing)return;
  if($('editorPanel').classList.contains('hidden')||document.querySelector('dialog[open]'))return;
  if(event.target.closest?.('input,textarea,select')||event.target.isContentEditable)return;
  const undo=(event.ctrlKey||event.metaKey)&&!event.shiftKey&&event.code==='KeyZ',plain=!event.ctrlKey&&!event.metaKey&&(event.key==='Backspace'||event.key==='Escape');
  if(undo||plain){event.preventDefault();event.stopImmediatePropagation();particleCancel()} // one pending point: Backspace, Esc and Ctrl+Z all remove it
},true);
// Both stages: Delete or Backspace removes the selection (or only the selected line); Esc clears the selection.
document.addEventListener('keydown',event=>{
  if(!particleActive()||particle.trace.length||busy||!state||event.ctrlKey||event.metaKey||event.altKey||event.isComposing||event.repeat)return;
  if($('editorPanel').classList.contains('hidden')||document.querySelector('dialog[open]'))return;
  if(event.target.closest?.('input,textarea,select')||event.target.isContentEditable||window.isPoreSelectionPending?.())return;
  if(!(window.getSelectedPores?.()||[]).length)return;
  if(event.key==='Delete'||event.key==='Backspace'){event.preventDefault();particleDeleteSelected()}
  else if(event.key==='Escape'){lineSel=null;window.clearPoreHighlight?.()}
});
const particleRender=renderMeasurements;
renderMeasurements=function(data){particleRender(data);if(data?.particle_width_mode){particleWidthMode=data.particle_width_mode;particleWidthShow()}particleSelUpdate();draw()};
new MutationObserver(()=>particleSelUpdate()).observe($('selectedPoreCount'),{childList:true,characterData:true,subtree:true}); // a table row click selects too
// Edit lines: every length and width line, two colours on a dark halo; length has bar ends, width round ends (colour is not the only cue).
// The selected line is thicker with white end handles. The live line uses the chosen axis colour, with small end dots, no numbers. Sized in screen pixels.
// End lines come from the server (`<axis>_caps`): parallel, equally long, and for a Feret width long enough to touch the particle.
let particleLabels=[]; // [{id, axis, x0, y0, x1, y1}] image px, refilled on every draw: a click on a label selects its line
function particleStroke(c,[a,b],axis,k,selected,caps,value,id){
  const color=particleColor(axis),w=(selected?3.5:2)*k,n=Math.hypot(b[0]-a[0],b[1]-a[1])||1,nx=-(b[1]-a[1])/n,ny=(b[0]-a[0])/n;
  const ends=Array.isArray(caps)&&caps.length===2?caps:[a,b].map(p=>[[p[0]-nx*5*k,p[1]-ny*5*k],[p[0]+nx*5*k,p[1]+ny*5*k]]);
  const path=()=>{c.beginPath();c.moveTo(...a);c.lineTo(...b);for(const [p,q] of ends){c.moveTo(...p);c.lineTo(...q)}};
  path();c.lineWidth=w+2.5*k;c.strokeStyle='rgba(6,8,12,.85)';c.stroke();
  path();c.lineWidth=w;c.strokeStyle=color;c.stroke();
  if(selected)for(const p of [a,b]){c.beginPath();c.arc(p[0],p[1],4.5*k,0,Math.PI*2);c.fillStyle='#fff';c.fill();c.lineWidth=1.5*k;c.strokeStyle='rgba(6,8,12,.9)';c.stroke()}
  if(value==null)return;
  // Value beside the line (L / W says which, so colour is not the only cue), on the side away from the image centre of the line pair.
  const text=(axis==='length'?'L ':'W ')+value.toFixed(2),size=12*k;
  c.font=`600 ${size}px "Segoe UI",system-ui,sans-serif`;c.textBaseline='middle';c.textAlign='center';
  // Beyond the line's end, outside the particle: the end nearer the image border loses, so labels stay on screen.
  const tw=c.measureText(text).width,th=size*1.35,ux=(b[0]-a[0])/n,uy=(b[1]-a[1])/n,reach=7*k+Math.abs(ux)*(tw/2+4*k)+Math.abs(uy)*th/2;
  const room=p=>Math.min(p[0],p[1],canvas.width-p[0],canvas.height-p[1]),atB=room(b)>=room(a),e=atB?b:a,sg=atB?1:-1;
  let cx=e[0]+sg*ux*reach,cy=e[1]+sg*uy*reach;
  cx=Math.max(tw/2+2*k,Math.min(canvas.width-tw/2-2*k,cx));cy=Math.max(th/2+2*k,Math.min(canvas.height-th/2-2*k,cy));
  const box={id,axis,x0:cx-tw/2-4*k,y0:cy-th/2,x1:cx+tw/2+4*k,y1:cy+th/2};particleLabels.push(box);
  c.fillStyle=selected?'#fff':'rgba(6,8,12,.78)';c.fillRect(box.x0,box.y0,box.x1-box.x0,box.y1-box.y0);
  c.lineWidth=1*k;c.strokeStyle=color;c.strokeRect(box.x0,box.y0,box.x1-box.x0,box.y1-box.y0);
  c.fillStyle=selected?'#111':color;c.fillText(text,cx,cy+.5*k);
}
const particleDrawBase=window.drawManualMeasurement;
window.drawManualMeasurement=c=>{
  particleDrawBase?.(c);
  if(!particleActive())return;
  const k=particleK();
  c.save();c.lineCap='round';c.setLineDash([]);
  particleLabels=[];
  if(particleStage==='lines')for(const r of particleRows())for(const axis of ['length','width']){
    const l=r[axis+'_line'];if(particleLineOk(l))particleStroke(c,l,axis,k,lineSel?.id===r.candidate_id&&lineSel.axis===axis,r[axis+'_caps'],r[axis+'_um'],r.candidate_id);
  }
  const pts=gesture?.moved&&gesture.button===0?gesture.points:particle.sent||(particle.trace.length&&particle.cursor?[particle.trace[0],particle.cursor]:particle.trace);
  if(pts.length){
    const color=particleColor(particleAxis);if(particle.sent&&!gesture)c.globalAlpha=.6;
    if(pts.length>1){c.beginPath();c.moveTo(...pts[0]);c.lineTo(...pts[1]);c.lineWidth=4.5*k;c.strokeStyle='rgba(6,8,12,.8)';c.stroke();c.lineWidth=2*k;c.strokeStyle=color;c.stroke()}
    for(const p of pts){c.beginPath();c.arc(p[0],p[1],3.5*k,0,Math.PI*2);c.fillStyle='rgba(6,8,12,.85)';c.fill();c.beginPath();c.arc(p[0],p[1],2.2*k,0,Math.PI*2);c.fillStyle=particleStage==='select'?'#fff':color;c.fill()}
  }
  c.restore();
};
labRailRender(null);window.labRailReady=true;labRailSample();
particleEditSet('select');particleAxisSet('length');
