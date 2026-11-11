"""Cropped lossless label snapshots and incremental screen patches."""
import copy
import json
from contextlib import nullcontext
import cv2
import numpy as np
from PIL import Image
from pore_editor import png_url
from export_folder_picker import documents_directory


def records(state, masks=None):
    masks = state['masks'] if masks is None else masks
    cache = state.setdefault('_label_records', {})
    result = {}
    for identifier, mask in masks.items():
        old = cache.get(identifier)
        if old is not None and old['mask'] is mask:
            result[identifier] = old; continue
        x,y,w,h = cv2.boundingRect(mask.astype(np.uint8))
        if not w or not h: raise ValueError('Cannot save an empty instance.')
        crop = np.ascontiguousarray(mask[y:y+h,x:x+w])
        yy,xx = np.nonzero(crop)
        distance = cv2.distanceTransform(np.pad(crop.astype(np.uint8),1),cv2.DIST_L2,3)[1:-1,1:-1]
        ly,lx = np.unravel_index(distance.argmax(),crop.shape)
        result[identifier] = dict(mask=mask,crop=crop,box=[x,y,w,h],packed=np.packbits(crop),area=int(crop.sum()),
            cx=float(xx.mean()+x),cy=float(yy.mean()+y),label=[int(lx+x),int(ly+y)])
    state['_label_records'] = result
    return result


def exclusive(state, masks, annotations):
    items = records(state,masks)
    occupied = np.zeros(state['gray'].shape,bool)
    overlaps = np.zeros_like(occupied)
    changed=[];removed=[];result={}
    order=sorted(items,key=lambda i:(annotations.get(str(i),{}).get('review_status')!='user_accepted',-items[i]['area'],i))
    for i in order:
        rec=items[i];x,y,w,h=rec['box'];region=occupied[y:y+h,x:x+w]
        conflict=rec['crop']&region
        if conflict.any():
            overlaps[y:y+h,x:x+w] |= conflict
            crop=rec['crop']&~region;changed.append(i)
            if not crop.any(): removed.append(i);continue
            mask=np.zeros_like(occupied);mask[y:y+h,x:x+w]=crop
        else: crop=rec['crop'];mask=masks[i]
        result[i]=mask;region |= crop
    return dict(sorted(result.items())),dict(overlap_pixels=int(overlaps.sum()),changed_ids=changed,removed_ids=removed)


def save(editor,state,masks,annotations,history,next_id,action,publish_guard=None):
    if action.get('type')!='undo':
        masks,cleanup=exclusive(state,masks,annotations)
        action=dict(action,overlap_cleanup=cleanup)
        for i in cleanup['changed_ids']:
            if str(i) in annotations: annotations[str(i)]=dict(annotations[str(i)],overlap_boundary_adjusted=True,review_status='boundary_adjusted_needs_review')
        for i in cleanup['removed_ids']: annotations.pop(str(i),None)
    items=records(state,masks)
    parent=editor.output_root/state['dataset'];parent.mkdir(parents=True,exist_ok=True)
    revision=max([int(p.name.split('_')[-1]) for p in parent.glob('revision_*') if p.is_dir()],default=0)+1
    folder=editor.revision_folder(state['dataset'],revision);folder.mkdir()
    ids=sorted(items)
    data=dict(shape=np.array(state['gray'].shape,np.int32),ids=np.array(ids,np.int64),boxes=np.array([items[i]['box'] for i in ids],np.int32).reshape(-1,4))
    data.update({f'm_{i}':items[i]['packed'] for i in ids})
    np.savez_compressed(folder/'label_crops.npz',**data)
    report=copy.deepcopy(state['report'])
    report.update(revision=revision,entrance_candidate_count=len(masks),candidate_annotations=annotations,report_deferred=True,
        label_storage='packed_crops_v1',candidates=[dict(candidate_id=i,area=items[i]['area']) for i in ids])
    (folder/'report.json').write_text(json.dumps(report),encoding='utf-8')
    meta=dict(revision=revision,parent_revision=state['revision'],history=history,next_id=next_id,annotations=annotations,action=action)
    (folder/'edit.json').write_text(json.dumps(meta),encoding='utf-8')
    pending=parent/'latest.pending.json';pending.write_text(json.dumps(dict(revision=revision)),encoding='utf-8')
    with publish_guard() if publish_guard else nullcontext():
        pending.replace(parent/'latest.json')
        state.update(masks=masks,annotations=annotations,history=history,next_id=next_id,revision=revision,preview=None,_fast_delta=True)
    return editor.response(state,include_measurements=False)


def snapshot(editor,state,revision):
    folder=editor.revision_folder(state['dataset'],revision)
    with np.load(folder/'label_crops.npz',allow_pickle=False) as data:
        shape=tuple(data['shape']);masks={}
        if shape != state['gray'].shape: raise ValueError('Label snapshot dimensions differ from the image.')
        for i,box in zip(data['ids'],data['boxes']):
            x,y,w,h=map(int,box)
            mask=np.zeros(shape,bool)
            mask[y:y+h,x:x+w]=np.unpackbits(data[f'm_{i}'],count=w*h).reshape(h,w).astype(bool)
            masks[int(i)]=mask
    meta=json.loads((folder/'edit.json').read_text(encoding='utf-8'))
    return dict(masks=masks,annotations=meta['annotations'],history=meta['history'],next_id=meta['next_id'],revision=revision,preview=None)


def response(editor,state):
    items=records(state);old=state.get('_sent_labels',{});delta=bool(state.pop('_fast_delta',False)) and bool(old)
    patches=[];candidates=[];sent={};scale=state['report']['scale']['um_per_pixel'];height,width=state['gray'].shape
    for i,rec in sorted(items.items()):
        annotation=state['annotations'].get(str(i),{});source=annotation.get('source','automatic')
        supplemental=annotation.get('supplemental',source in ('prompted_sam','manual_polygon','automated_sam'))
        sent[i]=(rec['mask'],supplemental)
        x,y,w,h=rec['box'];area=rec['area'];edge=x==0 or y==0 or x+w==width or y+h==height
        candidates.append(dict(candidate_id=i,area_pixels=area,area_um2=area*scale**2,equivalent_diameter_um=2*np.sqrt(area*scale**2/np.pi),centroid_x_pixels=rec['cx'],centroid_y_pixels=rec['cy'],touches_image_edge=edge,included_in_size_distribution=not edge,source=source))
        if delta and i in old and old[i][0] is rec['mask'] and old[i][1]==supplemental:continue
        if 'image' not in rec:
            rgba=np.full((h,w,4),255,np.uint8);rgba[:,:,3]=rec['crop']*255
            rec['image']=png_url(Image.fromarray(rgba))
            edges=np.zeros((h,w,4),np.uint8)
            contours,_=cv2.findContours(rec['crop'].astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(edges,contours,-1,(255,255,255,255),1)
            rec['edges']=png_url(Image.fromarray(edges))
        patches.append(dict(id=i,x=x,y=y,image=rec['image'],edges=rec['edges'],label=rec['label'],supplemental=supplemental))
    state['_sent_labels']=sent
    result=dict(fast_instances=True,instance_delta=delta,object_patches=patches,removed_ids=sorted(set(old)-set(items)) if delta else [],
        dataset=state['dataset'],revision=state['revision'],width=width,height=height,candidates=candidates,stats=None,
        measurements_current=False,can_undo=bool(state['history']),cut_paths_supported=True,report_ready=False,report_url=None,image_url=None,
        result_base=f"/files/{state['dataset']}/revision_{state['revision']:04d}",export_default_directory=str(documents_directory()),
        selection_settings=state['report'].get('selection_settings',{}),saved_folder=str(editor.revision_folder(state['dataset'],state['revision'])) if state['revision'] else None,
        workspace_mode='labeling',measurement_unit=state['report'].get('measurement_unit','px'),inference_device=editor.device)
    if not delta:
        if '_label_source_png' not in state:state['_label_source_png']=png_url(Image.fromarray(state['rgb']))
        result['image']=state['_label_source_png']
    return result
