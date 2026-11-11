import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
from PIL import Image
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
from cnt_train import eligible, label_maps, tips


def test_eligible_rule():
    assert eligible('CNT/261103', 'CNT_powder_1kx-29')
    assert eligible('CNT/261103', 'CNT_powder_100x-1')
    for stem in ('CNT_powder_1kx-30', 'CNT_powder_200x-31', 'CNT_powder_500x-38', 'CNT_powder_1kx', 'CNT_powder_500x', 'CNT_powder_1kx_'):
        assert not eligible('CNT/261103', stem)
    for stem in ('CNT_powder_1kx-30', 'CNT_powder_500x', 'anything'):
        assert eligible('CNT/261105', stem)
        assert eligible('CNT\\261105', stem)


def test_label_maps_prunes_touching_text(tmp_path):
    height, wide = 400, 600
    # a gently curved 300 px line whose middle runs into the label text, like `T1=12.3 um` in the user's images
    xs = np.arange(50, 351)
    line = np.column_stack([xs, 200+10*np.sin((xs-50)/300*np.pi)])
    two = np.zeros((height, wide, 3), np.uint8)
    cv2.polylines(two, [np.rint(line).astype(np.int32)], False, (255, 255, 0), 3)
    cv2.putText(two, 'T1=12.3 um', (200, 222), cv2.FONT_HERSHEY_SIMPLEX, .6, (255, 255, 0), 1)
    Image.fromarray(two).save(tmp_path/'x(2).tif')
    gray = np.full((height, wide), 40, np.uint8)
    C, t, w = label_maps(gray, tmp_path/'x(2).tif', height)
    assert ndi.label(C, np.ones((3, 3)))[1] == 1 and tips(C) == [2]
    assert (cKDTree(line).query(np.argwhere(C)[:, ::-1])[0] <= 2).all()
    assert C.sum() > 200
    yellow = (two[..., 0] > 150) & (two[..., 1] > 150)
    far_text = yellow & (ndi.distance_transform_edt(~C) > 7.5) & (np.arange(height)[:, None] > 215)   # the lower part of the text, clear of the line
    assert far_text.sum() > 20 and (w[far_text] == 0).all()
    assert t[C].min() == 1 and w[C].min() == 1
