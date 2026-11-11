import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import numpy as np
import pytest
from lab_geometry import object_path, manual_geometry
from lab_geometry import centered_geometry, report_geometry
from lab_geometry import automatic_center, center_connected_path


def test_two_points_follow_bent_object():
    mask = np.zeros((100, 100), bool)
    mask[10:81, 10:20] = True
    mask[70:81, 10:81] = True
    mask[10:81, 70:81] = True
    path = object_path(mask, [[15, 15], [75, 15]])
    assert mask[path[:, 1].astype(int), path[:, 0].astype(int)].all()
    result = manual_geometry({'manual_measurements': {'length': path.tolist()}})
    assert result['length_pixels'] > 150  # Endpoints are only 60 px apart.
    assert np.isnan(result['width_pixels'])


def test_disconnected_endpoints_are_rejected():
    mask = np.zeros((30, 30), bool)
    mask[2:8, 2:8] = True
    mask[20:26, 20:26] = True
    with pytest.raises(ValueError, match='disconnected'):
        object_path(mask, [[4, 4], [23, 23]])


def test_drawn_path_sums_segments():
    result = manual_geometry({'manual_measurements': {'length': [[0, 0], [3, 4], [6, 0]], 'width': [[0, 0], [0, 2]]}})
    assert result['length_pixels'] == 10
    assert result['width_pixels'] == 2


def test_automatic_center_follows_bent_object():
    mask = np.zeros((100, 100), bool)
    mask[10:81, 10:21] = True
    mask[70:81, 10:81] = True
    mask[10:81, 70:81] = True
    g = centered_geometry(mask)
    cx, cy = np.floor(np.array(g['center_point'])+.5).astype(int)
    assert mask[cy, cx]
    assert g['length_pixels'] > 150
    assert 9 <= g['width_pixels'] <= 12
    width = np.array(g['width_line'])
    assert np.allclose(width[1], g['center_point'])
    assert abs(width[0, 0]-width[-1, 0]) < 1


def test_compact_center_and_manual_override():
    yy, xx = np.mgrid[:51, :51]
    mask = (xx-25)**2+(yy-25)**2 <= 15**2
    g = centered_geometry(mask)
    assert np.linalg.norm(np.array(g['center_point'])-[25, 25]) < 2
    assert 27 < g['length_pixels'] < 33
    assert 27 < g['width_pixels'] < 33
    corrected = report_geometry(mask, {'manual_measurements': {'length': [[0, 0], [3, 4]]}})
    assert corrected['length_pixels'] == 5
    assert np.isnan(corrected['width_pixels'])


def test_endpoint_paths_share_automatic_center_without_automatic_lengths():
    mask = np.zeros((61, 81), bool)
    mask[10:51, 10:71] = True
    center = automatic_center(mask)
    first = center_connected_path(mask, [[10, 15], [70, 15]])
    second = center_connected_path(mask, [[25, 10], [25, 50]])
    for path in (first, second):
        assert np.any(np.all(path == center, axis=1))
        assert mask[path[:, 1].astype(int), path[:, 0].astype(int)].all()
    unmeasured = report_geometry(mask, {})
    assert np.isnan(unmeasured['length_pixels'])
    assert np.isnan(unmeasured['width_pixels'])
    assert unmeasured['center_point'] == center.tolist()
