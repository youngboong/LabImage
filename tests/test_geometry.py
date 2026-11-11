import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import cv2
import numpy as np
from lab_geometry import geometry


def test_rectangle_pixel_extent_and_scale():
    mask=np.zeros((100,180),bool);mask[30:50,20:140]=True
    result=geometry(mask)
    assert abs(result['width_pixels']-20)<.01
    assert 115 < result['length_pixels'] < 126
    assert result['skeleton_components']==1


def test_compact_object_has_meaningful_longitudinal_size():
    mask=np.zeros((100,100),np.uint8);cv2.circle(mask,(50,50),20,1,-1)
    result=geometry(mask.astype(bool))
    assert 38 < result['length_pixels'] < 43
    assert 38 < result['width_pixels'] < 43
    assert result['length_method']=='max_feret_compact_object'


def test_curve_longer_than_chord_and_thin_width_finite():
    mask=np.zeros((180,180),np.uint8)
    cv2.ellipse(mask,(90,90),(60,60),0,10,170,1,9)
    result=geometry(mask.astype(bool))
    assert result['length_pixels'] > 150
    assert result['length_pixels'] > result['max_feret_pixels']
    single=np.zeros((8,8),bool);single[3,3]=True
    assert geometry(single)['width_pixels']==1


def test_translation_does_not_change_measures():
    mask=np.zeros((90,150),bool);mask[8:18,6:86]=True
    other=np.zeros((160,220),bool);other[48:58,36:116]=True
    a,b=geometry(mask),geometry(other)
    assert abs(a['length_pixels']-b['length_pixels'])<1e-9
    assert abs(a['width_pixels']-b['width_pixels'])<1e-9
