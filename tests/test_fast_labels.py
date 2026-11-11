import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
from lab_editor import LabEditor


def test_packed_snapshots_delta_delete_undo(tmp_path):
    editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')
    first = np.zeros((37, 43), bool)
    first[2:15, 3:17] = True
    first[5:8, 6:9] = False
    second = np.zeros_like(first)
    second[20:31, 23:40] = True
    state = dict(dataset='test', gray=np.zeros(first.shape, np.uint8), rgb=np.zeros((*first.shape,3),np.uint8),
        report=dict(workspace_mode='labeling',scale=dict(um_per_pixel=1)), masks={},annotations={},history=[],next_id=301,revision=0)
    initial = editor.save(state,{1:first,300:second},{},[],301,dict(type='test'))
    assert initial['fast_instances'] and not initial['instance_delta']
    restored = editor.snapshot(state, state['revision'])
    assert np.array_equal(restored['masks'][1],first)
    assert np.array_equal(restored['masks'][300],second)
    changed=first.copy();changed[3,3]=False
    delta=editor.save(state,{1:changed,300:second},{},[state['revision']],301,dict(type='test'))
    assert delta['instance_delta'] and 'image' not in delta
    assert [p['id'] for p in delta['object_patches']]==[1]
    deleted=editor.mutate(state,dict(revision=state['revision'],target_ids=[300]),'delete')
    assert deleted['removed_ids']==[300] and not deleted['object_patches']
    editor.mutate(state,dict(revision=state['revision']),'undo')
    assert np.array_equal(state['masks'][300],second)
    editor.mutate(state,dict(revision=state['revision'],target_ids=[1,300]),'delete')
    assert editor.snapshot(state,state['revision'])['masks']=={}


def test_overlap_cleanup_preserves_unchanged_identity():
    from lab_fast_labels import exclusive
    a=np.zeros((20,20),bool);a[2:12,2:12]=True
    b=np.zeros_like(a);b[8:18,8:18]=True
    masks,cleanup=exclusive(dict(gray=np.zeros(a.shape)),{1:a,300:b},{'300':{'review_status':'user_accepted'}})
    assert masks[300] is b
    assert not (masks[1]&masks[300]).any()
    assert np.array_equal(masks[1]|masks[300],a|b)
    assert cleanup['overlap_pixels']==16
