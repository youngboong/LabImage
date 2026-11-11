"""Benchmark an isolated copy of an existing labeling state; never edit user data."""
import copy, json, sys, time
from pathlib import Path
import cv2
import numpy as np
from lab_editor import LabEditor

root=Path(__file__).resolve().parents[1]
tag=sys.argv[1] if len(sys.argv)>1 else 'before'
source=LabEditor(output_root=root/'LabImage-data/outputs/manual_edits',project_root=root/'LabImage-data/outputs/projects',device='intel-gpu')
dataset='image_30a3f4cab6b595f9__run_0001'
state=copy.deepcopy(source.state(dataset))
editor=LabEditor(output_root=root/f'validation/click-{tag}/manual_edits',project_root=root/'LabImage-data/outputs/projects',device='intel-gpu')
editor.states[dataset]=state
times={}
for name in ['preview','preview_masks','save','response']:
    original=getattr(editor,name)
    def timed(*a,_f=original,_n=name,**kw):
        start=time.perf_counter()
        try:return _f(*a,**kw)
        finally:times[_n]=times.get(_n,0)+time.perf_counter()-start
    setattr(editor,name,timed)
identifier=max(state['masks'],key=lambda k:state['masks'][k].sum())
y,x=np.unravel_index(cv2.distanceTransform(state['masks'][identifier].astype(np.uint8),cv2.DIST_L2,3).argmax(),state['gray'].shape)
results=[]
for n in range(4):
    times.clear();start=time.perf_counter()
    result=editor.quick_segment(state,dict(dataset=dataset,revision=state['revision'],points=[[int(x),int(y)]],labels=[1],target_id=identifier,auto_apply=True))
    row=dict(total=time.perf_counter()-start,**times,response_bytes=len(json.dumps(result)))
    results.append(row);print(n,row,flush=True)
data=dict(shape=list(state['gray'].shape),objects=len(state['masks']),runs=results,warm_median_seconds=float(np.median([r['total'] for r in results[1:]])))
(root/f'validation/click-{tag}.json').write_text(json.dumps(data,indent=2),encoding='utf-8')
