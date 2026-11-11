# CNT tube measurement: implementation design

Status: implementation-ready spec for phase 1. It follows `docs/cnt-plan.md` with the decisions below. A deviation from the plan is marked **[deviation]**, with its reason.

## Scope change (supersedes the parts of this spec below that conflict)

Fully automatic tube detection was removed after the prototype showed it recovers too few labelled tubes (§2.4). Phase 1 is the Tube (T) tool only:

- **Removed:** `detect_tubes`, `refine_ends`, flags / `certain` / `confidence`, `public`, the Find tubes / Select certain / Add selected panel, candidate overlay and hover, `/api/detect-tubes`, `/api/add-tubes`, the auto-recall metric and its tests.
- **Kept:** ridge filter (computed lazily on the first trace, cached in `state['tube_cache']`, which is the `ridge_response` dict itself), `trace_tube`, `measure_mask`, width, T#/D# labels, export `tube` key.
- **Tube tool:** click one end, then the other end. The backend traces the ridge. Shift-click adds waypoints (max 20 points). Enter finishes, Backspace removes a point, Esc cancels. Ctrl-click segments with SAM and measures the mask (replaces the "nothing near" fallback of D4).
- **`/api/trace-tube`** now saves the traced tube at once as one new object (one revision, one Ctrl+Z) and returns the normal editor response plus `object_id`, `length`, `width`, `unit`, `length_px`, `width_px`. There is no preview step. A tube whose band is fully covered by existing masks returns `This tube is already measured.`
- **`/api/measure-tube`** is unchanged, and returns the same extra fields. Its response width is the length of the saved width line (what the table and CSV show), not the 5-station median.
- **Evaluation** (`scripts/cnt_eval.py`) is trace-based only: traces are seeded from GT tips; gates are assisted recall, median length error and width-method error.
- **Oriented tracker (`cnt_detect` VERSION 2, replaces the ridge geodesic of §3.4).** The tubes at 1kx are flattened ribbons, 15–30 px wide. Their edges are bright, their interior is darker, and they often cross other fibres. The v1 geodesic on the sato cost hugged one bright edge and switched strands at crossings. Now:
  1. Width `w` is the median of `width_at` taken 8–32 px inside both end clicks. The direction into the tube is the strongest sato ray, of length `3w`.
  2. Each click pair is searched in a box with margin `|b−a|+3w`. The box is downsampled to a lattice (≤ `TRACK_MAX_CELLS` cells). On it, 8 zero-mean oriented line filters run at widths `w·(0.6, 1, 1.6)`: +band of the width, −flanks, length 1.5× the width. Each width is normalised by its 97th percentile; the max is taken over widths.
  3. Dijkstra (`scipy.sparse.csgraph`) runs over (cell, 16 headings). Moves are one step along the current heading or a ±22.5° bend. Step cost is `1/(0.05+clip(r,0,2)^2)` × length. A bend adds `0.5·w`. The band filter peaks at the ribbon centre, not at an edge. The bend cost makes the path go straight through crossings. After a waypoint, the next segment starts from the arrival heading, with the same bend cost.
  4. Each node is moved to sub-cell precision with a parabola across its heading. Then a Savitzky–Golay pass smooths the path (window `1.5w`). `finish_candidate` measures width and length as before.

  The lattice is always connected, so there is no geodesic fallback. With 2 interior waypoints on the 24 certain GT tubes (≥1kx), the median symmetric distance to GT went from 8.3 to 5.5 px and recall from 0.75 to 0.92. The remaining errors come from U-shaped tubes clicked only at their two ends: the cheapest path then takes a shorter, real neighbouring fibre, so the user must add a Shift-click on the right strand. Wide bundles that were labelled with a straight line also fail. About 0.1 s per segment.

- **Object kinds, clean-section D, label placement (supersede the 5-station median and the nearest-gap labels).**
  - `/api/trace-tube` takes `kind`: `td` (default), `t` (length only) or `d` (width only, exactly one point). The reply nests tube values under `tube` (`kind, length_px, width_px, length, width, unit, clean`); the top-level `width` is the image width again. Annotation keys follow the kind (`manual_measurements` has only `length`, only `width`, or both); `tube.kind` records it.
  - D (`cnt_detect.tube_width`): stations every ~W/3 along the smoothed path, outer 15% skipped. Each station is scored on edge sharpness, left/right symmetry, centring, a flat dark band of 1xW outside both edges (no neighbouring or crossing fibre), steadiness of the tube body along the tube, local straightness (+-W) and agreement with neighbouring stations (15%). D is the median width of the best contiguous run (+-2 stations); the width mark is drawn at the best station, with its length set to that median, so table, CSV and figure agree. No station with quality >= `SECTION_QMIN` (0.40) gives `width_px = None` and no D. `tube.width_station = {s, fraction, quality, clean, stations}`. The mask band uses the whole-tube width (`prelim_px`), not the section width.
  - Width only (`measure_spot`): snaps the click to the strongest oriented response within ~W (6 widths x 8 headings), takes that heading, traces +-3W, and measures the clean section nearest the click. When no section is clean it still measures the best station and reports `clean: false`.
  - Labels (`lab_geometry.place_tube_label`): candidates sit beside the label's own line (both sides, ends, diagonals; gap 5-12 px, far fallback 18-70 px), inside the image, off every mask, drawn line and label. A box is unambiguous when the nearest line of ANOTHER tube is >= max(2 x own distance, own distance + 15 px). Crowded objects are placed first; labels near another label are penalised. A thin leader to the own line is drawn only when no unambiguous spot exists.

Target reader: the coding agent. Every file:line reference was checked against the current sources. The originals are in `backup_before_cnt/`. Do not touch `source/`, `_internal/`, `dist/`, `build/` or `PoreSAM/`.

---

## 0. Decisions (fixed for phase 1; the user can revise them)

| # | Decision |
|---|---|
| D1 | Width = median of 5 station widths. The saved width line is drawn at the station whose width is closest to that median. |
| D2 | Labels use the object ID: `T{id}=…` for length and `D{id}=…` for width (T3 and D3 belong to the same tube). |
| D3 | Scope is isolated tubes. Any magnification is accepted; the best results are expected at 1kx–3kx. Bundles are out of scope. |
| D4 | Click: snap to the nearest detected centerline first (any candidate, certain or rejected). If nothing is near, use a SAM mask, then measure it automatically. **[addition]** Shift-click points give a 2+-point ridge trace (§3.4). Prototype data shows this is the tool that works in tangles. |
| D5 | Scale reuses the existing calibration (`state['report']['scale']['um_per_pixel']`, footer and scale-bar detection already run in `lab_workflow.inspect`). No OCR. |
| D6 | Crossing tubes may share pixels in their *measurements*. **[deviation]** Stored masks stay exclusive: `Editor.save` enforces `overlap_pixels(...) == 0` (`scripts/pore_editor.py:415-422`), and that invariant is used by apply, labeling export and the overlap tools. Changing it is out of scope. Centerline and width are computed on the unclipped tube *before* the mask is carved, so both crossing tubes keep their full length and width. Only the tint mask loses the crossing patch. |
| D7 | The existing Add (A) tool is unchanged. Report mode is also used for particles, and auto-measuring every SAM object would change their figures. The SAM fallback runs only inside the new Tube tool. **[deviation from plan §1.5]** |

---

## 1. Verified facts about the existing code

### 1.1 State and annotation schema

- State dict (`pore_editor.Editor.state`, `scripts/pore_editor.py:172-185`, extended by `LabEditor.state`, `scripts/lab_editor.py:23-31`). It holds:
  - `dataset`, `report`, `gray` (uint8, ROI only, already cut at `analysis_bottom_exclusive`), `rgb`, `sam_gray`;
  - `masks` (dict int → bool HxW), `annotations` (dict **str** id → dict), `history` (list of revisions), `next_id`, `revision`, `preview`.
  - Per-dataset in-memory caches live in the same dict (for example `geometry_cache`, `measurements`, `queued_previews`). The new `tube_cache` follows that pattern.
- Calibration (`scripts/lab_workflow.py:71-72, 139-140`):
  - Uncalibrated runs use `scale_um=1, scale_pixels=1`, so `um_per_pixel == 1`, and set `report['measurement_unit'] == 'px'`.
  - Calibrated runs use `'µm'`.
  - Use `state['report'].get('measurement_unit', 'µm') == 'px'` as the "uncalibrated" test. Older datasets have no key and count as calibrated.
- Manual measurement schema (`scripts/lab_editor.py:98-100`):
  - `annotations[str(id)]['manual_measurements'][axis] = [[x, y], ...]`, image px, x = column.
  - `annotations[str(id)]['measurement_methods'][axis] = method`.
  - `axis ∈ {'length', 'width'}`.
  - `reset_automatic` pops both keys (`:70-77`).
- Consumers of these keys:
  - `report_geometry` (`scripts/lab_geometry.py:220-230`) re-routes only methods `object_path` / `object_path_via_center` through `center_connected_path`. Any other method string falls through to `manual_geometry` (`:233-241`), which sums the stored path. A missing axis gives `NaN`. **New methods `auto_centerline` / `auto_width` need no change there.**
  - `measure_masks` (`scripts/analyze_candidates.py:52-56`) calls `report_geometry` in report mode. CSV `length_um` / `width_um` follow automatically.
  - `measured_overlay` (`scripts/lab_geometry.py:244-333`) calls `report_geometry` per object (`:293-295`). It draws paths, end caps (`:305-322`), outside value labels (`:323-326`), the center dot (`:327-329`) and the `#id` label (`:330-332`).
  - `lab_export.export_images` (`scripts/lab_export.py:66-74`) writes `measurement_paths[id] = {center, paths, methods}` into `measurements.json`. `report_composer.py:137-138` reuses `measured_overlay`.
- Revisions and undo:
  - `Editor.save(state, masks, annotations, history, next_id, action)` (`scripts/pore_editor.py:412-445`) writes `revision_NNNN/` with `entrance_candidates.npz` and `edit.json`, and returns `self.response(state, include_measurements=False)`.
  - `LabEditor.save` (`scripts/lab_editor.py:51-56`) drops `geometry_cache` and goes to the labeling fast path only in labeling mode.
  - Undo is `mutate(...,'undo')` (`scripts/pore_editor.py:478-481`). It restores `snapshot(history[-1])`, so **one save = one Ctrl+Z step**.
  - The UI binds Ctrl+Z to `/api/undo` (`ui/editor.html:191-199`) when there is no pending preview or input history.
- API routing (`scripts/lab_editor.py:161-213`):
  - LabImage routes are whitelisted by the tuple on line 173. The rest falls through to `pore_editor.make_handler`.
  - Checks run in this order: host + `X-Object-Editor` header (`:175-176`), Origin (`:177-179`), size ≤ 1 MB (`:181-182`), `workflow.running` (`:184`), `editor.lock` + `state` + `check_revision` (`:185-187`), then dispatch (`:188-205`).
  - `ValueError` / `KeyError` / `TypeError` return 400 with `{error}`. Anything else returns 500.

### 1.2 Frontend (`ui/labimage.js`, loaded last by `ui/editor.html:212`)

- Globals from `ui/editor.html`:
  - `state`, `mode`, `busy`, `canvas` (`:42`);
  - `setStatus(text, error)` (`:46`), `controls()` (`:47`), `api(route, payload)` (`:48`), `work(message, fn)` (`:49`), `image()` (`:50`);
  - `draw()` (`:54-71`, calls `window.drawManualMeasurement?.(ctx)` at `:64`), `eventPoint(e)` → `[x, y]` image px (`:73`);
  - the pointerdown dispatcher (`:82`), which calls `window.handleLabPointer?.(e)` first; `accept(data)` (`:137`); `payload()` → `{dataset, revision}` (`:158`).
- Patterns to copy:
  - Panel injection: `manualPanel` is created and inserted with `labMeasurements.before(manualPanel)` (`ui/labimage.js:270-282`). Class `panel lab-report-only` hides it in labeling mode (`ui/labimage.css:3`).
  - Tool button: `labDeleteTool` (`ui/labimage.js:44-55`), a `[data-mode]` button inserted into `#tools`, with an onclick that switches `mode`.
  - Pointer hook: `window.handleLabPointer` (`:191-198`). Wrap it; return `true` when handled.
  - Hotkeys: map `{KeyS:'select', KeyA:'positive', KeyD:'delete'}` (`:213`). It clicks `[data-mode=…]`.
  - Enter/Esc listener (`:223-227`). Every `[data-mode]` click calls `manualStop` (`:336`).
  - `controls` wrapper (`:113-117`). `controls()` sets `disabled = busy` on *every* button. Custom disabled states must be re-applied in a wrapper.
  - `window.onEditorAccepted` chain (`:136-144`, `:344-353`). Wrap it again; always call the previous one.
  - `window.drawManualMeasurement` (`:337-343`). Wrap it to draw candidates.
  - SAM click flow in report mode (`:166-189`): `quick-segment` returns a preview + `token`, then `apply` with `{token, choice: 0, target_id}`. The new id is the candidate not present before (`:181-183`).

### 1.3 Baseline tests (recorded 2026-11-09)

- `.venv/Scripts/python.exe -m pytest tests -q` gives **13 passed, 2 errors**. Both errors are `PermissionError` creating pytest's temp dir `C:\Users\Public\Documents\ESTsoft\CreatorTemp\pytest-of-krict` (environment, not code).
- With a writable temp dir, `.venv/Scripts/python.exe -m pytest tests -q -p no:cacheprovider --basetemp <writable dir>` gives **15 passed**. Use that form if the default fails the same way.

---

## 2. Prototype findings (ground truth for the defaults)

Throwaway scripts are in `C:\Users\krict\AppData\Local\Temp\claude\0a6ed2706a870218\33f00c26-2165-4a73-8a4c-acc194192970\scratchpad\proto\` (`v2.py`, `v3.py`, `auto2.py`, `width*.py`, `synth.py`, `ends.py`). Data: all 21 labelled base images ≥1kx in `CNT/261103` and `CNT/261105`. The ROI is 1024×768.

1. **Scale.** `um_per_pixel = 279.0/1024 × 1000/mag` (FoV 279 µm at 1kx). This matches the bar (50 µm / 183 px = 0.2732) and the FoV text at 2kx (140 µm) and 3kx (93.1 µm). Used only by the evaluation, because 5 images have no detectable bar.
2. **GT length extraction is exact once simplified.** Skeleton geodesic → `approximate_polygon(tol=1.5)` → chord sum, times scale:
   - `1kx-6`: 264.93 µm vs label `T1=265.30 µm`;
   - `1kx-9`: 364.68 vs `365.08`.
   - The raw skeleton overestimates by 5–6 %.
   - GT width pairing reproduces `1kx-12 D2 = 8.01 µm` (29.4 px).
3. **Ridge response.** Five-scale `sato` takes 0.7–1.0 s per image on CPU.
   - Global Otsu on R misses faint ribbons: the thresholded mask covers about 60 % of GT tube pixels.
   - Robust hysteresis (median + 3/6 MAD) keeps most isolated tubes as one component.
4. **Fully automatic detection is weak on this data.**
   - 24 simple GT tubes (2-tip polylines, ≥60 px) at ≥1kx. Only 2–3 were matched by a candidate (coverage and precision ≥ 70 %), 2 of them unflagged.
   - Length error was about 1 % when matched.
   - Causes: user-labelled tubes usually run into tangles, and faint thin ribbons fragment.
   - About 9 unflagged candidates per image; precision is unknown because the user labels only a few tubes.
   - Junction straight-through merging and tip-to-tip gap linking were both tried. Neither helped measurably, so both are dropped (simplicity).
5. **Ridge trace between two clicks works.** Geodesic on cost `1/(0.05 + clip(R/otsu, 0, 2))`, clicks at the GT tips, 24 tubes:
   - median |length error| 5.5 %, bias −1.6 %;
   - with one extra via-click: 4.5 %;
   - about 2 % when the trace stays on the tube.
   - Each trace takes 0.03–0.09 s.
6. **Width.** Profile across the tube, level = bg + 0.25·(peak − bg), outermost crossings, start window ±8 µm, then 2 refinements (half = 0.75·w + 6). Against 53 GT marks: median |error| 13.9 %, bias +2 %. FWHM (level 0.5) fails on ribbons (bright edges, dim core): median 32 %, it measures one edge.
7. **Ends.** `geometry()`'s boundary extension on the *ridge* mask overshoots by +5–7 % on synthetic tubes, because the ridge mask is wider and longer than the tube. Without extension it is −2…−4 %. Intensity-based end refinement (§3.3) gives 0–2.1 %.
8. **Synthetic tubes** (600×800, σ=1 blur, noise σ=6, 1kx scale):

   | Case | Detector length vs arc+w | Trace length vs arc | Width |
   |---|---|---|---|
   | straight, w20 | 0.0 % | −1.1 % | +2.5 px |
   | S-curve, w20 | 2.1 % | −2.8 % | +2.8 px |
   | ribbon, w24 | 1.5 % | −4.4 % | +4.5 px |
   | thin, w8 | 0.7 % | −0.9 % | +2.8 px |

   Flags: a crossing pair gave `branched`; a tube touching the edge gave `border`.

**Consequence for the design:** "Find tubes" is a convenience that finds the few clean isolated tubes per image. The workhorse is the Tube tool: click to snap, or Shift-click to trace. The evaluation reports both (§6).

---

## 3. Backend: `scripts/cnt_detect.py` (new, pure numpy/scipy/skimage/cv2, no state)

### 3.1 Constants (module level, in this order)

```python
VERSION = 1
TUBE_WIDTH_UM = (1.5, 16.0)          # expected tube widths, calibrated
TUBE_WIDTH_PX = (8.0, 68.0)          # uncalibrated ('px' unit) fallback
SIGMA_COUNT = 5
SIGMA_PER_RADIUS = 1/1.7             # sato sigma ≈ radius/1.7
SIGMA_CLAMP = (1.5, 20.0)
BACKGROUND_SIGMA = 40.0              # flat-field: f - gaussian(f, 40)
PRE_SMOOTH_SIGMA = 1.5
HYST_LOW_MAD, HYST_HIGH_MAD = 3.0, 6.0
MIN_COMPONENT_PX = 300
BORDER_MARGIN_PX = 2
BRANCH_MIN_PX = 15.0                 # off-path skeleton piece >= max(15, 3 r) -> branched
SHORT_MIN_PX = 40.0                  # length < max(40, 10 r) -> short
MAX_CANDIDATES = 300
TRACE_EPS, TRACE_CLIP = 0.05, 2.0
TRACE_SNAP_PX = 6
TRACE_MAX_POINTS = 20
DECIMATE_STEP = 3                    # keep every 3rd vertex (+ last) of the 1-px path
END_LEVEL = 0.5
WIDTH_STATIONS = (0.20, 0.35, 0.50, 0.65, 0.80)
WIDTH_LEVEL = 0.25
WIDTH_HALF0_UM, WIDTH_HALF0_PX = 8.0, 30.0
WIDTH_HALF_CLAMP = (10.0, 120.0)
WIDTH_REFINE = 2
WIDTH_STEP = 0.25                    # profile sample spacing, px
WIDTH_OFFSETS = (-3, -2, -1, 0, 1, 2, 3)   # parallel profiles along tangent, px
WIDTH_SMOOTH_PX = 1.5
WIDTH_MIN_CONTRAST = 4.0             # gray levels, peak - background
BAND_PER_SIGMA = 3.5                 # mask band when no width: 3.5 x median sigma
```

### 3.2 Functions and signatures

Path convention everywhere: `np.ndarray` of shape `(N, 2)`, columns **x, y**, float image px in ROI coordinates (the same as `manual_measurements`).

```python
def sigmas_for(um_per_pixel: float, calibrated: bool) -> list[float]
```
- Radius range in px:
  - calibrated: `(TUBE_WIDTH_UM[0]/2/um_per_pixel, TUBE_WIDTH_UM[1]/2/um_per_pixel)`;
  - otherwise: `TUBE_WIDTH_PX / 2`.
- Return `np.geomspace(max(1.5, rmin*SIGMA_PER_RADIUS), min(20, rmax*SIGMA_PER_RADIUS), 5)`.
- Reference values: 1kx (0.2725) → [1.6, 2.9, 5.3, 9.6, 17.3]; 2kx → [3.2, 5.1, 8.0, 12.7, 20]; 3kx → [4.9, 6.9, 9.9, 14.0, 20]; uncalibrated → [2.4, 4.0, 6.9, 11.8, 20].
- If `rmin*SIGMA_PER_RADIUS > 20` (very high magnification), use `[20.0]*1` and accept a poor fit.

```python
def ridge_response(gray: np.ndarray, um_per_pixel: float, calibrated: bool) -> dict
```
- Computation:
  - `f = gray/255 (float32)`; `f -= gaussian(f, BACKGROUND_SIGMA)`; `f = gaussian(f, PRE_SMOOTH_SIGMA)`.
  - For each sigma: `skimage.filters.sato(f, sigmas=[s], black_ridges=False)`. Stack the results; `R = max`, `sigma = sigmas[argmax]`.
  - Statistics: `median = median(R)`, `mad = 1.4826*median(|R-median|)` (floor at 1e-6), `otsu = threshold_otsu(R[R>0])`.
- Returns `dict(R=float32 HxW, sigma=float32 HxW, sigmas=list, median, mad, otsu, um_per_pixel, calibrated, cost=float32 HxW)`, where `cost = 1/(TRACE_EPS + clip(R/otsu, 0, TRACE_CLIP))`.

```python
def detect_tubes(gray: np.ndarray, ridge: dict) -> list[dict]
```
Steps 1–4 build the mask. Step 5 runs per component. Step 6 sorts.
1. `M = apply_hysteresis_threshold(R, median + 3·mad, median + 6·mad)`.
2. `M = binary_opening(M)` (default 3×3 cross, 1 iteration).
3. `M = remove_small_objects(M, MIN_COMPONENT_PX)`.
4. `M = binary_fill_holes(M)`.
5. Label 8-connected. For each component `comp` (crop by `find_objects`, `(y0, x0)` offset):
   1. `g = lab_geometry.geometry(comp, compact_fallback=False, extend_ends=False)`. The new parameter is in §4.1. Skip the component if `len(g['length_path']) < 2`. `raw = np.asarray(g['length_path']) + [x0, y0]`.
   2. `r = median(distance_transform_edt(comp)[skeletonize(comp)])`. This is the ridge-mask radius, about 1.7× the true radius; it is used only for windows and flags.
   3. Branched check:
      - Draw `raw - [x0, y0]` with `cv2.polylines(…, thickness=2*int(2r+2)+1)` into `near`.
      - `off = skeletonize(comp) & ~near`. Label 8-connected.
      - `branched = any(piece.sum() >= max(BRANCH_MIN_PX, 3r))`.
   4. `cand = finish_candidate(gray, ridge, raw, source='detector', refine_radius=r)`.
   5. Flags, in this fixed order when present:
      - `border`: component bbox within `BORDER_MARGIN_PX` of any ROI edge (top, left, right, or bottom = `gray.shape[0]`);
      - `branched`;
      - `short`: `cand['length_px'] < max(SHORT_MIN_PX, 10r)`;
      - `low_contrast`: `median(R at rounded path pixels) < median + 6·mad`.
   6. `cand['confidence'] = clip(median(R on path)/(median+6·mad)/3, 0, 1)` rounded to 3 decimals.
6. Sort: unflagged first, then `length_px` descending. Truncate to `MAX_CANDIDATES`.

```python
def trace_tube(gray: np.ndarray, ridge: dict, points: list) -> dict
```
- `2 ≤ len(points) ≤ TRACE_MAX_POINTS`, each `[x, y]` finite and inside the image. Otherwise `ValueError('Trace needs 2 to 20 points inside the image.')`.
- **Superseded (VERSION 2): see "Oriented tracker" in the Scope change section.** The old v1 rule was: snap each point to the max of `R` within 6 px, then route each pair with `MCP_Geometric(ridge['cost'])`. It hugged one bright edge of the ribbon and switched strands at crossings.
- Points closer than 1 px: `ValueError('Choose distinct trace points.')`.

```python
def measure_mask(gray: np.ndarray, mask: np.ndarray, ridge: dict) -> dict
```
- Used by the SAM fallback.
- `g = geometry(mask, compact_fallback=False)` with the default `extend_ends=True`. The SAM mask boundary is the tube boundary, so its extension is correct.
- `raw = g['length_path']`. If `len(raw) < 2`, raise `ValueError('Cannot trace a centerline in this object.')`.
- Return `finish_candidate(gray, ridge, raw, source='sam', refine_radius=None)`. Flags are `[]`.

```python
def finish_candidate(gray, ridge, raw_path, source, refine_radius=None) -> dict
```
1. `p = resample(raw_path, 1.0)`: arc-length resampling at 1 px with `np.interp`.
2. `w = odd(max(3, round(2*median(ridge['sigma'] at p))))`. `p = smooth_path(p, w)`.
3. If `refine_radius`: `p = refine_ends(gray, p, refine_radius)`.
4. Clip to `[0, W-1] × [0, H-1]`.
5. `width = tube_width(gray, p, ridge['um_per_pixel'], ridge['calibrated'])`. This uses the 1-px path.
6. `path = decimate(p)`: `p[::DECIMATE_STEP]` plus the last point if it was not included. `length_px = sum(|diff(path)|)`. **Length is always computed from the stored path**, so the UI, the CSV (`manual_geometry`) and the candidate agree exactly.
7. `band_px = width['width_px'] if width['width_px'] else BAND_PER_SIGMA*median(sigma on p)`.
8. Return the internal candidate:
   ```python
   dict(source=source, path=path, length_px=float, width_px=float|None, width_line=[[x,y],[x,y]] or [],
        width_stations=[float|None]*5, band_px=float, flags=[], confidence=None)
   ```

```python
def smooth_path(p, window) -> np.ndarray
```
Moving average per coordinate, `np.pad(mode='edge')`, kernel `ones(window)/window`. Keep `p[0]` and `p[-1]` exactly as given. If `len(p) <= window`, return `p` unchanged.

```python
def refine_ends(gray, p, r) -> np.ndarray
```
- `gs = gaussian(gray.astype(float), 1.0)`. For each end:
  1. `inner = p[min(round(3r), n-1)]` (or mirrored for the last end). `d = unit(p_end - inner)`.
  2. Samples `p_end + s·d` with `s ∈ arange(-3r, 3r+0.5, 0.5)`, `map_coordinates(order=1, mode='nearest')`.
  3. `peak = median(first quarter)`, `bg = median(last sixth)`, `level = bg + END_LEVEL·(peak-bg)`.
  4. `stop = first s (index > len/4) with profile < level`, else `3r`.
  5. If `stop ≥ 0`, append (or prepend) `p_end + stop·d`. If `stop < 0`, truncate the 1-px path by `|stop|` px at that end, keeping ≥ 2 points.
- If `peak - bg < WIDTH_MIN_CONTRAST`, leave the end unchanged.

```python
def profile_width(gray, center, tangent, half) -> tuple[float, np.ndarray, np.ndarray] | None
```
1. `n = (-tangent[1], tangent[0])`, `t = arange(-half, half + WIDTH_STEP, WIDTH_STEP)`.
2. Profile = mean over `WIDTH_OFFSETS` of `map_coordinates(gray_f, [y, x], order=1, mode='nearest')` along `center + s·tangent + t·n`.
3. `gaussian_filter1d(profile, WIDTH_SMOOTH_PX/WIDTH_STEP)`.
4. `q = max(4, len//8)`; `bg = median(concat(profile[:q], profile[-q:]))`.
5. Core = central half; `peak = core.max()`. Return `None` if `peak - bg < WIDTH_MIN_CONTRAST`.
6. `above = profile >= bg + WIDTH_LEVEL·(peak-bg)`.
7. `lo, hi` = outermost `above` samples with `|t| ≤ 0.8·half`, extended to cover the whole connected `above` run that contains the core maximum.
8. Return `(t[hi]-t[lo], center + t[lo]·n, center + t[hi]·n)`.

```python
def width_at(gray, center, tangent, um_per_pixel, calibrated) -> tuple | None
```
- `half = WIDTH_HALF0_UM/um_per_pixel` if calibrated else `WIDTH_HALF0_PX`, clipped to `WIDTH_HALF_CLAMP`.
- `r = profile_width(...)`; then up to `WIDTH_REFINE` times, if `r`: `r = profile_width(..., half=clip(0.75·r[0]+6, *WIDTH_HALF_CLAMP))`. Return `r`.
- The evaluation also uses this at the GT marks.

```python
def tube_width(gray, p, um_per_pixel, calibrated) -> dict
```
- For each fraction in `WIDTH_STATIONS`:
  - station = arc-length interpolation on `p`;
  - tangent = `point(s+5) - point(s-5)` (clamped to `[0, L]`, normalized);
  - `width_at(...)`.
- `valid` = non-None widths. If `valid` is empty, return `dict(width_px=None, width_line=[], width_stations=[None]*5)`.
- Otherwise: `width_px = median(valid)`, and `width_line = [p_lo, p_hi]` of the station whose width is closest to the median (D1).
- `width_stations` keeps `None` for failed stations. Round to 2 decimals.

```python
def tube_mask(shape, path, band_px) -> np.ndarray   # bool
```
`cv2.polylines(zeros uint8, [rint(path).astype(int32)], False, 1, thickness=max(3, int(round(band_px))))`, returned as bool.

```python
def public(candidate: dict, index: int) -> dict
```
JSON wire form (§5.1). All floats rounded to 2 decimals; `path` becomes a `.tolist()` of rounded values.

---

## 4. Edits to existing files

### 4.1 `scripts/lab_geometry.py`

1. `geometry` signature (`:15`): `def geometry(mask, compact_fallback=True, extend_ends=True):`.
   - Line 93 becomes `elif extend_ends and len(path) > 1:`.
   - Defaults are unchanged, so existing callers and tests are unaffected.
2. `measured_overlay` (`:290-332`). Per object:
   - Read `annotation = state.get('annotations', {}).get(str(identifier), {})` and `tube = 'tube' in annotation`.
   - Build `lines` entries as `(path, value, fraction, prefix)`: `prefix = f'T{identifier}=' if tube else ''` for length, and `f'D{identifier}=' if tube else ''` for width.
   - Label text: `f'{prefix}{value*scale:.2f} {unit}'` (`:326`). This matches the user's `T1=151.12 µm`.
   - End caps for tube objects: skip the mask ray-march (`:313-320`) and use fixed reaches.
     - Length path: `[cap, cap]`, where `cap = max(8., font_size*.7)` as now.
     - Width line: `[max(cap, .6*value)]*2`, so the two caps form the user's "two parallel lines".
     - Reason: width-line endpoints sit on the mask edge, so the ray along the tube can run the full tube length.
   - Skip the center dot (`:327-329`) for tube objects.
   - Skip the `#id` label (`:332`) for tube objects when `show_length or show_width`, because T/D already carry the id.
   - Non-tube objects render exactly as before.

### 4.2 `scripts/lab_export.py`

Line 72-74 dict: add `tube=annotation.get('tube')`. This one key carries the provenance: stations, flags, confidence and source.

### 4.3 `scripts/lab_editor.py`

New module-level helper and `LabEditor` methods, placed after `manual_measurement`. Use lazy imports, `from cnt_detect import …`, as the file already does for heavy modules.

```python
def tube_annotation(c):          # c: internal candidate
    measurements = {'length': c['path'].tolist()}
    methods = {'length': 'auto_centerline'}
    if c['width_px'] is not None:
        measurements['width'] = c['width_line']; methods['width'] = 'auto_width'
    return dict(source={'detector': 'cnt_ridge_detector', 'trace': 'cnt_trace', 'sam': 'prompted_sam'}[c['source']],
                supplemental=True, review_status='user_accepted',
                manual_measurements=measurements, measurement_methods=methods,
                tube=dict(version=VERSION, candidate_source=c['source'], width_stations=c['width_stations'],
                          flags=c['flags'], confidence=c['confidence']))
```

- `tube_cache(self, state)`:
  - If not report mode: `ValueError('Tubes are available in report mode.')`.
  - Lazily creates `state['tube_cache'] = dict(ridge=ridge_response(state['gray'], um_per_pixel, calibrated), candidates=None)`. Gray never changes within a dataset, so the cache survives revisions and undo.
- `detect_tubes(self, state, payload)`:
  - If `cache['candidates'] is None`, set it to `detect_tubes(state['gray'], cache['ridge'])`.
  - Return `dict(dataset, revision, um_per_pixel, unit, candidates=[public(c, i) for i, c in enumerate(cache['candidates'])])`.
  - A repeat call returns the cache, including traced candidates.
- `trace_tube(self, state, payload)`:
  - `points = payload.get('points')`.
  - First check `isinstance(points, list) and 2 <= len(points) <= 20`, else `ValueError('Trace needs 2 to 20 points inside the image.')`.
  - Then call `self.coords(points, state['gray'].shape)` (`pore_editor.py:271-277`). It raises `Invalid coordinates.` or `Place points inside the image.`, and the API passes those messages through unchanged.
  - Ensure `candidates` is detected first, so indices are stable.
  - Append `trace_tube(...)` and return `dict(candidate=public(c, index))`.
- `add_tubes(self, state, payload)`:
  1. `indices = payload.get('indices')`. Require a list of 1–200 unique `int` values (`type(i) is int`), each `0 ≤ i < len(candidates)`. Otherwise `ValueError('Invalid tube selection.')`.
  2. `masks = dict(state['masks'])`, `annotations = copy.deepcopy(state['annotations'])`, `next_id = state['next_id']`, `occupied = OR of masks`.
  3. For each index in the given order:
     - `m = tube_mask(shape, c['path'], c['band_px']) & ~occupied`.
     - If `m.sum() < 20`, append `{index, reason: 'already measured'}` to `skipped` and continue.
     - Otherwise `masks[next_id] = m`, `occupied |= m`, `annotations[str(next_id)] = tube_annotation(c)`, record `{index, object_id: next_id}` in `added`, and increment `next_id`.
  4. If nothing was added: `ValueError('Selected tubes are already measured.')`.
  5. `result = self.save(state, masks, annotations, list(state['history']) + [state['revision']], next_id, dict(type='add-tubes', added=added, skipped=skipped))`, then `result.update(added=added, skipped=skipped)`.
  - Pre-carving keeps `exclusive_existing` a no-op. Existing objects never lose pixels, and no annotation gets `boundary_adjusted_needs_review`.
- `measure_tube(self, state, payload)`:
  - Validate `object_id` exactly as `manual_measurement:67-69`.
  - `c = measure_mask(state['gray'], state['masks'][id], cache['ridge'])`.
  - Deep-copy the annotations. Set `manual_measurements`, `measurement_methods` and `tube` from `tube_annotation(c)`, keeping the existing `source` and other keys.
  - `self.save(..., dict(type='tube-measurement', object_id=id))`. The mask is unchanged.
- `make_handler.do_POST`:
  - Extend the tuple at `:173` with `'/api/detect-tubes', '/api/trace-tube', '/api/add-tubes', '/api/measure-tube'`.
  - Add dispatch branches before the `else` at `:192`: `self.path == '/api/detect-tubes'` → `editor.detect_tubes(state, payload)`, and the same for the others.
  - Security, size, `running` and revision checks are inherited unchanged.

---

## 5. API contract

All routes take `POST` with a JSON body `{dataset, revision, ...}` and the header `X-Object-Editor: 1` (the frontend `api()` already sends it). Errors return `400 {error}`. The message strings are listed per route.

| Route | Extra body | Success body | Revision? | Errors |
|---|---|---|---|---|
| `/api/detect-tubes` | none | `{dataset, revision, um_per_pixel, unit, candidates: [Candidate]}`. Empty list when none. | no | not report mode; stale revision (`Results changed in another session. Reload the image.`) |
| `/api/trace-tube` | `points: [[x,y], …]` (2–20) | `{candidate: Candidate}` (`source:"trace"`, `flags:[]`) | no | `Trace needs 2 to 20 points inside the image.`; `Choose distinct trace points.` |
| `/api/add-tubes` | `indices: [int, …]` (1–200) | the normal editor response (same as `apply`) + `added: [{index, object_id}]`, `skipped: [{index, reason}]` | **yes, one** | `Invalid tube selection.`; `Selected tubes are already measured.` |
| `/api/measure-tube` | `object_id: int` | normal editor response | **yes, one** | `Choose a segmented object first.`; `Cannot trace a centerline in this object.` |

### 5.1 Candidate (wire)

```json
{
  "index": 7,
  "source": "detector",
  "centerline": [[412.0, 133.5], [414.8, 134.9], "..."],
  "length_px": 412.63,
  "width_px": 18.31,
  "width_line": [[530.2, 120.4], [524.9, 137.9]],
  "width_stations": [17.9, 18.31, null, 19.04, 18.12],
  "flags": ["branched"],
  "certain": false,
  "confidence": 0.62
}
```

- `certain == (flags == [])`.
- `width_px` may be `null`; then `width_line` is `[]`.
- `confidence` is `null` for trace and SAM candidates.
- The frontend converts to physical units with `um_per_pixel` from `/api/detect-tubes`.

### 5.2 Saved annotation (in `edit.json` and `report.json` `candidate_annotations`)

```json
"12": {
  "source": "cnt_ridge_detector",
  "supplemental": true,
  "review_status": "user_accepted",
  "manual_measurements": {"length": [[412.0, 133.5], "..."], "width": [[530.2, 120.4], [524.9, 137.9]]},
  "measurement_methods": {"length": "auto_centerline", "width": "auto_width"},
  "tube": {"version": 1, "candidate_source": "detector", "width_stations": [17.9, 18.31, null, 19.04, 18.12],
           "flags": ["branched"], "confidence": 0.62}
}
```

`source` is `cnt_trace` for traces. For the SAM fallback, the `prompted_sam` source written by `apply` is kept.

### 5.3 Undo semantics

| User action | Ctrl+Z steps |
|---|---|
| Add selected | 1 step removes all tubes added in that batch. |
| SAM fallback | 2 steps: `apply`, then `tube-measurement`. The first Ctrl+Z restores the unmeasured object; the second removes it. |
| Find tubes, trace, selection toggles | No revision, so nothing to undo. Pending trace points are cleared with Esc or Backspace, not Ctrl+Z. |

Undo restores `annotations` from the snapshot, so the `tube` key and the measurements disappear together.

- Correcting a tube with the endpoint tools overwrites that axis and its method, and keeps `tube`, so the labels stay T/D.
- "Clear saved measurements" pops only the measurement keys, so the object shows automatic geometry with T/D labels.

---

## 6. UI (`ui/labimage.js`): functional spec only (styling comes later)

### 6.1 Markup hooks

- Panel `<section id="tubePanel" class="panel lab-report-only">`, inserted with `manualPanel.before(tubePanel)` after `manualPanel` exists. Contents:
  - `h2` "Tubes";
  - buttons `#tubeFind`, `#tubeSelectCertain`, `#tubeClearSelection`, `#tubeAdd` (text `Add selected (k)`);
  - checkbox `#tubeShowRejected` inside a `label.row`;
  - `<p id="tubeStatus" class="hint" role="status">`;
  - `<p id="tubeHint" class="hint">` with the tool help text.
- Tool button `<button id="tubeTool" data-mode="tube" class="lab-report-only">Tube (T)</button>`, inserted in `#tools` before `[data-mode="negative"]`, following the `labDeleteTool` pattern (`:44-55`).
- All colors, dash patterns and badge sizes go in one `const TUBE_STYLE = {...}` object at the top of the block, so the redesign step changes them in one place.

### 6.2 Client state

```js
let tube = {dataset: null, ump: 1, unit: 'px', items: [], selected: new Set(), added: new Map() /* index -> object_id */, trace: []};
```

- In the `onEditorAccepted` wrapper: if `data.dataset !== tube.dataset`, reset everything.
- Otherwise drop `added` entries whose `object_id` is no longer in `data.candidates`. After an undo, those candidates show again.

### 6.3 States and controls

- `idle` (no items): `#tubeFind` enabled; Select certain, Clear and Add are disabled. Status: "Find tubes, or use the Tube tool (T)."
- `found`: status `"{c} certain · {r} rejected"` plus `" · {k} selected"` when k > 0. Select certain is enabled when c > 0; Clear and Add are enabled when k > 0.
- `tracing` (`tube.trace.length > 0`): status `"Trace · {n} points · click to finish, Shift-click to add, Enter finish, Backspace undo point, Esc cancel"`.
- `busy`: global `controls()` disables everything. Re-apply the rules above in a `controls` wrapper (same pattern as `:113-117`).

### 6.4 Actions

- **Find tubes** → `work('Finding tubes…', …)`, `api('detect-tubes', payload())`. Store `items`, `ump`, `unit` and `dataset`, then `draw()`.
- **Select all certain** → `selected = indices of certain items not in added`.
- **Clear** → empty `selected` and `trace`.
- **Add selected** → `api('add-tubes', {...payload(), indices: [...selected]})`, then `accept(response)`. Move each `added` entry into `tube.added`, clear `selected`, and refresh the measurement table: `renderMeasurements(await measurementSnapshot())`, as `manualSave` does at `:310-314`. Status: `"Added {n} tubes · {m} skipped · Ctrl+Z to undo"`.
- **Show rejected** checkbox → `draw()`.

### 6.5 Tube tool pointer behavior

Wrap `window.handleLabPointer` and handle `mode === 'tube'`, returning `true`. With `p = eventPoint(e)`:
1. If `tube.items` is empty and no trace is pending, run Find tubes first, then continue.
2. `e.shiftKey`: push `p` onto `tube.trace` (max 20), then `draw()`.
3. Plain click with `tube.trace.length ≥ 1`:
   - push `p`, then call `api('trace-tube', {...payload(), points: tube.trace})`;
   - append the candidate to `items`, add it to `selected`, clear `trace`;
   - status `"Traced #{index} · L … · W … · Add selected to save"`.
4. Plain click otherwise: find the nearest non-added item (certain or rejected, visible or not) by point-to-polyline distance. If it is ≤ `max(8, (width_px||16)/2 + 4)` image px, toggle its selection. A selected rejected candidate is drawn even when Show rejected is off.
5. Otherwise, SAM fallback inside `work('Segmenting with SAM 2.1…')`:
   - `quick-segment` with `{points: [p], labels: [1], target_id: null, auto_apply: true}`;
   - `apply` with `{token, choice: 0, target_id: null}`;
   - find the new id as at `:181-183`;
   - `measure-tube` with `{object_id}`;
   - `accept(...)`.
   - Status: `"Measured object #{id} from SAM mask · Ctrl+Z twice removes it"`.

### 6.6 Hover

When `mode === 'tube'` and nothing is busy, a canvas `pointermove` finds the nearest item, using the same tolerance as §6.5 step 4. It sets the status to:

`#{index} · L {length·ump:.2f} {unit} · W {width·ump:.2f|—} {unit} · {flags.join(', ') || 'certain'}`

### 6.7 Drawing

Wrap `window.drawManualMeasurement`; call the previous hook first. Report mode only. Draw:
- every non-added item that is certain, selected, or rejected with Show rejected on;
- certain: dashed; selected: solid; rejected: grey dashed;
- an index badge at the arc midpoint;
- the pending trace points as dots joined by a thin dashed line.

### 6.8 Keyboard

- Add `KeyT: 'tube'` to the map at `:213`.
- In a new keydown listener with the same guards as `:210-212` (inputs, dialogs, busy), and only when `mode === 'tube'` and `tube.trace.length`:
  - `Enter` with ≥ 2 points runs the trace with the current points;
  - `Backspace` pops the last point;
  - `Escape` clears the trace. The existing Esc handler also runs `labResetPrompt`, which is harmless.
- Ctrl+Z is unchanged.

### 6.9 Not changed

`editor.html`, `labimage.css` (except later restyling), the Add (A) tool, and labeling mode.

---

## 7. Evaluation harness: `scripts/cnt_eval.py` (dev tool, not shipped)

### 7.1 CLI

```
.venv/Scripts/python.exe scripts/cnt_eval.py [--folders CNT/261103 CNT/261105] [--min-mag 1000]
                                             [--images NAME ...] [--out validation/cnt-eval]
```

- Defaults are as shown.
- It prints the summary table and the PASS/FAIL lines.
- Exit code is 0 even on FAIL. It is a report, not a test.

### 7.2 Discovery and scale

- For each folder, take files whose lowercase name ends with `(2).tif`. The base is the same name with `(2)` removed.
  - Skip the file if the base is missing. This skips the orphans `CNT_powder_1kx-5.(2).TIF` and `CNT_powder_500(2).tif`.
  - The `(3)` file is optional.
- Magnification: regex `_(\d+(?:\.\d+)?)(k?)x` on the base name; `k` means ×1000. Skip the image if the regex fails or `mag < --min-mag`.
- `um_per_pixel = 279.0/1024*1000/mag`. Use `calibrated=True`.
- `gray = L(base)[:detect_information_footer(L(base))]`. This gives 768 rows for most images and 818 for the 6 old-layout ones.

### 7.3 GT extraction

Yellow mask on the RGB `(2)`/`(3)` image, cropped to the ROI: `R>150 & G>150 & B<110 & min(R,G)-B>60`.

**Lengths, from `(2)`:**
1. 8-connected components with bbox extent ≥ 60 px. Text glyphs are smaller.
2. `skeletonize`. Tips = skeleton pixels with exactly 1 skeleton neighbour.
3. **Simple GT**: exactly 2 tips. Path = `MCP_Geometric(where(sk, 1, inf))` traceback tip→tip, converted to x, y. `gt_length = chord sum of approximate_polygon(path, 1.5)`.
4. Components with more than 2 tips are **complex GT** (crossing or touching polylines). They are counted and drawn, but excluded from the metrics.
5. **Certain GT** = simple, `gt_length ≥ 60`, and bbox ≥ 5 px from every ROI edge.

**Widths, from `(3)`:**
1. Components with extent ≥ 25 px that are line-like: SVD of the pixel coordinates, `s1/s0 ≤ 0.15`. Record the center, direction `d` and length `L`.
2. Pair each segment with the nearest unpaired segment such that:
   - `|d1·d2| ≥ 0.98`;
   - `|L1-L2| ≤ 0.2·max(L)`;
   - along-offset `≤ 0.5·L1`;
   - perpendicular distance `≤ 150` px.
3. For each mark: `gt_width` = perpendicular distance, `mid` = midpoint of the two centers, `tangent = d1`.
4. D# numbering in the user's images is independent of T#. Match by location only.

### 7.4 Pipelines and matching

- **Auto**: `detect_tubes(gray, ridge)`.
- **Assisted** (simulates two clicks): for each certain GT, `trace_tube(gray, ridge, [tipA_xy, tipB_xy])`.
- **Match** between a candidate and a GT path:
  - `tol = max(6, 0.75·(width_px or 16))`;
  - coverage = fraction of GT points within `tol` of the candidate (cKDTree) ≥ 0.70;
  - precision = fraction of candidate points within `tol` of the GT ≥ 0.70.
  - Points are 1-px resampled on both sides.
- Auto counts as recovered when any candidate matches. It counts as "certain-recovered" when an unflagged one matches; pick the best |length error| if several match.

### 7.5 Metrics

Computed per image and pooled.

| Metric | Definition |
|---|---|
| `auto_recall_certain` | Certain GT matched by an unflagged candidate / certain GT. Also report `auto_recall_any`. |
| `assisted_recall` | Certain GT whose trace matches / certain GT. |
| Length relative error | `L_pred/gt_length − 1`, for assisted (gate) and for auto-matched (report): median \|e\|, p90 \|e\|, median signed e. |
| `width_method_error` | `width_at(gray, mid, tangent, ump, True)` vs `gt_width` at every GT mark (gate): median \|e\|, p90, bias. |
| `width_reported_error` | For each GT mark whose `mid` is within `max(6, w/2+4)` px of a matched or traced tube centerline: that tube's reported `width_px` (median of stations) vs `gt_width` (report). |
| Other counts | Unflagged candidates per image; runtime per image (ridge, detect, traces). |

### 7.6 Acceptance targets

The caller's targets, gated on certain GT at ≥1kx:

| Target | Threshold | Expected from prototype |
|---|---|---|
| `assisted_recall` | ≥ 0.80 | borderline |
| `auto_recall_certain` | ≥ 0.80 | **≈0.1, expected FAIL in phase 1** |
| median \|length error\| (assisted) | ≤ 5 % | ≈5–6 %, borderline |
| median \|width_method_error\| | ≤ 15 % | ≈14 %, borderline |

The report must state these baselines so the user can decide whether to revise the auto target or fund phase 2: per-tube SAM masks, or a learned tube detector.

### 7.7 Outputs (in `--out`, created if missing)

- `report.md`:
  - run date, parameters (`cnt_detect.VERSION` and constants);
  - summary table with PASS/FAIL;
  - per-image table: image, mag, µm/px, certain GT, complex GT, unflagged candidates, auto matched, assisted matched, median length error, median width error, seconds;
  - the list of skipped files.
- `per_tube.csv`: one row per certain GT tube and per GT width mark, with all errors.
- `<base-stem>.png`: one overlay per image on the ROI RGB:
  - GT polylines in yellow; GT width marks in orange;
  - unflagged candidates in cyan; flagged candidates thin grey;
  - assisted traces in magenta;
  - candidate index text.

---

## 8. Tests: `tests/test_cnt_detect.py`

Use the same `sys.path` header as `tests/test_manual_paths.py:1-4`.

### 8.1 Synthetic renderer (helper in the test file)

- `render(curves, shape=(600, 800), ribbon=False, seed=0)`. `curves` is a list of `(path_xy (N,2), width_px)`.
- Per curve:
  - `m = cv2.polylines(zeros uint8, [rint(path)], False, 1, thickness=int(width))`;
  - `d = distance_transform_edt(m)`.
  - Plain tube: `img = max(img, 50 + 110·clip(d/1.5, 0, 1))`.
  - Ribbon: `img = max(img, where(m, 110, 0) + where((d>0)&(d<3), 60, 0))`.
- Start from `img = 50`. Then `gaussian(img, 1)` + `normal(0, 6)` with `default_rng(seed)`, clip, cast to uint8.
- `ump = 0.2725`, `calibrated = True`. `arc(path)` = polyline length.
- Curves:
  - straight: `x = 100 + 500t, y = 300`;
  - S-curve: `x = 100 + 550t, y = 300 + 120·sin(2πt)` (arc ≈ 754);
  - vertical crossing: `x = 400, y = 80 + 440t`;
  - border: `x = 400t, y = 200 + 100t`.
  - `t = linspace(0, 1, 400)`.

### 8.2 Cases and tolerances

Tolerances are grounded on §2.8 with about 1 % or 1 px of headroom. Width tolerance: `|w - w0| ≤ 0.2·w0 + 2`. Length tolerance: relative.

| Test | Input | Assert |
|---|---|---|
| `test_sigmas_scale_with_calibration` | `sigmas_for` at 0.2725 / 0.0908 / uncalibrated | 5 values, ascending, within [1.5, 20]; first value grows with magnification |
| `test_straight_tube_is_certain` | straight, w20 | exactly one certain candidate; mean distance of its centerline to the truth ≤ 3 px; `|L/(arc+w) − 1| ≤ 0.03`; width tolerance |
| `test_s_curve_length_and_width` | S-curve, w20 | certain; `≤ 0.03`; width tolerance; `len(width_stations) == 5`; `width_line` endpoints straddle the true centerline |
| `test_ribbon_tube` | ribbon S-curve, w24 | certain; `≤ 0.03`; width tolerance |
| `test_thin_tube` | S-curve, w8 | certain; `≤ 0.03`; width tolerance |
| `test_crossing_pair_flags_and_trace_goes_straight` | straight w20 + vertical w14 | candidate covering the straight tube has `branched`; `trace_tube` from straight's two ends: `|L/arc − 1| ≤ 0.05`, median distance to the true line ≤ 3 px |
| `test_border_tube_flagged` | border, w16 | the matching candidate has `border` |
| `test_trace_validation` | 1 point, 21 points, out-of-image point, same point twice | `ValueError` |
| `test_measure_mask_sam_fallback` | mask = `cv2.polylines` band (w20) of the S-curve, gray = render | `|L/(arc+w) − 1| ≤ 0.03`; width tolerance |
| `test_add_tubes_overlay_export_undo` | LabEditor integration (below) | see below |

Integration test setup:
- `editor = LabEditor(output_root=tmp_path/'edits', project_root=tmp_path/'projects', device='cpu')`, as in `tests/test_fast_labels.py:9`.
- `state = dict(dataset='t', gray=g, rgb=stack3(g), report=dict(workspace_mode='report', image='x.png', scale=dict(um_per_pixel=.2725), measurement_unit='µm'), masks={}, annotations={}, history=[], next_id=1, revision=0)`, where `g` = straight + S-curve far apart.

Steps:
1. `detect_tubes` returns ≥ 2 certain candidates.
2. `add_tubes` with their indices: 2 masks; each annotation has `measurement_methods == {'length': 'auto_centerline', 'width': 'auto_width'}` and a `tube` key; `manual_geometry(annotation)['length_pixels'] == candidate length_px` (approx 1e-6).
3. `measured_overlay(state)` returns an image of the gray's size.
4. `editor.measurements(state)['candidates']` has finite `length_um`.
5. A second `add_tubes` with the same indices raises `ValueError('…already measured.')`.
6. `editor.mutate(state, dict(revision=state['revision']), 'undo')` gives `state['masks'] == {}`.

Run with `.venv/Scripts/python.exe -m pytest tests -q`. If tmp-dir permissions fail as in the baseline, add `-p no:cacheprovider --basetemp <writable dir>`. Expected: **15 old + 10 new pass**; the runtime increase should be ≤ 15 s.

---

## 9. Ordered implementation steps (each step must pass its check before the next)

1. **Geometry flag.** Add `extend_ends` to `lab_geometry.geometry`.
   - Check: existing 15 tests pass.
2. **Ridge + trace core.** `cnt_detect.py` constants, `sigmas_for`, `ridge_response`, `smooth_path`, `trace_tube` (with a minimal `finish_candidate`: resample, smooth, decimate, length).
   - Check: `test_sigmas_*`, `test_trace_validation`, and the trace part of the crossing test.
3. **Width.** `profile_width`, `width_at`, `tube_width`, `tube_mask`, full `finish_candidate`, `public`.
   - Check: width asserts of the trace-based tests.
   - Quick script: `width_at` on `CNT_powder_1kx-12(3)` mark D2 ≈ 29 px ±15 %.
4. **Detection.** `refine_ends`, `detect_tubes`, `measure_mask`.
   - Check: all `tests/test_cnt_detect.py` pure tests.
   - Time `detect_tubes` on `CNT/261103/CNT_powder_1kx-12.tif`: ≤ 3 s.
5. **Backend API.** `lab_editor.py` methods + routes.
   - Check: the integration test.
6. **Figure and export.** `measured_overlay` T/D labels, caps, dot, id; `lab_export` `tube` key.
   - Check: all tests.
   - Manually export one figure from a test state (call `measured_overlay` in a script, save PNG, look at it).
7. **UI.** Panel, tool, drawing, keyboard in `labimage.js`.
   - Check:
     - run the app (`.venv/Scripts/python.exe scripts/pore_app.py --device cpu`);
     - Report mode on `CNT_powder_1kx-9.tif`: Find tubes; click-select; Shift-click + click trace along the long tube; Add; Ctrl+Z; re-add; SAM fallback on an empty spot near a tube;
     - Save Images, and check that `measurements.csv` and `measurements.json` contain the tubes with `auto_centerline`;
     - no entries in `window.labErrors`.
8. **Evaluation.** `scripts/cnt_eval.py`.
   - Check: run on default folders; `validation/cnt-eval/report.md` and PNGs exist; numbers are close to §2. Record PASS/FAIL. Do not tune constants to the evaluation set without noting it in the report.
9. **Regression.** Full `pytest tests -q`.
   - Optional: `scripts/lab_selftest.py` (needs the SAM checkpoint) to confirm non-tube report figures are unchanged.

---

## 10. Known limitations and risks

- Auto-detection recall on the user's labelled tubes is low (§2.4). Most labelled tubes touch tangles. The assisted trace and the snap-to-rejected-candidate click are the intended path.
- The trace can short-cut through a neighbouring bright fibre (about ⅔ of 2-click traces deviated somewhere by >15 px, yet the median length error stays about 5 %). Mitigation: Shift-click via points. The overlay shows the path before Add, so the user can see it.
- Width uses the 25 % level of the outer profile. On synthetic blurred tubes it reads +2–3 px wide; on real ribbons the bias is +2 %. Frayed or flattened bundles remain noisy (p90 error about 40 %).
- Masks are exclusive (D6). The crossing patch is tinted for only one tube; the measurements are unaffected.
- Thresholds are fixed constants. A sensitivity slider is deliberately not added; revisit only if the evaluation shows image-to-image failures.
- `tube_cache` is in memory only. After an app restart, Find tubes recomputes it (about 1 s).
