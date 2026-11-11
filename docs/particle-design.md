# Particle (flake) length / width measurement: design

Status: design + prototype only (2026-11-11). Prototype code: `validation/particle-proto/` (`gt.py`, `sam_cache.py`, `proto.py`, `click.py`). No product code changed.

## 1. Data facts

- Folder `261110_704113_powder`: 43 originals (41 at 300x, plus `SWCNT_704113_1kx-10.tif` at 1000x and `21.tif`), 1024 x 946 px, grey. Flat flakes on a dark substrate; the substrate also shows large faint "charging" regions with bright outlines (300x_3, 300x_6 left side).
- Information bar: starts at **row 768** (a uniform grey rule, value 99, std 0). Image area = rows 0..767.
- **`lab_footer.detect_information_footer` returns 818 on 35 of 43 images** (768 on 8). It skips the first bar row (Energy/Mag/FoV cells). Particle code must not trust it as is: rows 768..817 would be treated as image (cut-off test against the wrong bottom, masks on bar text). Fix or work around before shipping (see Risks).
- Scale at 300x: 931 um / 1024 px = **0.9092 um/px**. Confirmed from labels: caliper widths match the printed values to 0.05 um (D1 90.46, D3 69.05, D4 47.29); capped lines measure 0.5..1 um above the printed value because the pixel extent includes the 1-px end caps. Scale must still come from the project calibration (the folder holds a 1kx image).
- Two label styles exist:
  - 300x_3, 300x_10: one 1-px #ffff00 straight line with short perpendicular end caps, value text "269.33 µm" beside it, on background.
  - 300x-31 width: two parallel tangent lines + dotted perpendicular + "+" centre, text "D1=90.46 µm" (another tool's caliper). Length lines are the capped style.

## 2. Ground truth (extracted by `gt.py`)

px = pixel extent of the drawn line; um = px x 0.9092; "label" = printed value where read.

| Image | P | Length line (x,y)->(x,y) | L px | L um (label) | Width line | W px | W um (label) |
|---|---|---|---|---|---|---|---|
| 300x_3 | 1 | (709,332)->(839,295) | 134.9 | 122.65 (121.97) | (769,269)->(802,356) | 92.7 | 84.28 (83.40) |
| 300x_3 | 2 | (417,496)->(709,440) | 297.1 | 270.12 (269.33) | (568,374)->(600,561) | 189.6 | 172.38 (171.38) |
| 300x_10 | 1 | (598,251)->(630,592) | 342.5 | 311.39 | (527,449)->(718,429) | 191.9 | 174.47 (173.64) |
| 300x_10 | 2 | (242,577)->(178,675) | 117.3 | 106.65 | (177,620)->(255,648) | 82.5 | 75.01 (74.16); 76 deg to L, not 90 |
| 300x_10 | 3 | (609,686)->(863,680) | 254.1 | 231.02 | (734,602)->(743,751) | 149.3 | 135.74 (134.76) |
| 300x-31 | 1 | (422,115)->(509,208) | 127.4 | 115.83 (115.12) | caliper | 52.0 | 47.28 (D4=47.29) |
| 300x-31 | 2 | (546,122)->(613,180) | 88.6 | 80.55 (79.86) | caliper | 55.2 | 50.19 (D2=50.13) |
| 300x-31 | 3 | (811,240)->(1007,155) | 213.2 | 193.84 (193.33) | caliper | 99.5 | 90.46 (D1=90.46) |
| 300x-31 | 4 | (552,624)->(699,631) | 147.2 | 133.83 (132.85) | caliper | 76.0 | 69.10 (D3=69.05) |

Observation: in the capped style the width line crosses the **middle of the length line**, perpendicular, outline to outline. GT extraction pitfalls handled in `gt.py`: value text touching the line (Hough + refit to 1-px band), several lines in one component (peeled one by one), small 45-degree caliper lines (component size cut 22 px).

## 3. Detection method: SAM 2.1 automatic masks (chosen)

Compared on all 43 images:

- **Threshold** (local median background, +10 grey, close/fill/open): fails. Flake interiors are often no brighter than the substrate; touching flakes merge. Found 4 of 9 GT particles, and only 2 with a usable outline. Rejected.
- **SAM automatic masks**, LabImage Labeling settings (`points_per_side=16`, `pred_iou_thresh=.7`, `stability_score_thresh=.85`, smallest-first exclusive resolve as in `lab_workflow.py`): one clean mask per flake, touching flakes separated (300x_3 P2 and its overlapping neighbour are two masks). Found **9 of 9** GT particles. `points_per_side=32` (CPU, 47 s/image) gave the same GT numbers; not worth it.
- Click-to-segment: `SAM2ImagePredictor.predict(point_coords=[[x,y]], multimask_output=True)`, take the highest-score mask, keep the connected component under the click. Same masks and numbers as automatic on all 9 GT particles.

Runtime (Intel GPU, OpenVINO): automatic 5.5 s/image median (pps 16, batch 1) + < 0.1 s features; click: 0.6 s image encode once, then ~20 ms per click.

## 4. Exact definitions

On the mask's outer contour, using pixel corners (each contour pixel +-0.5 px), convex hull:

- **Length** = maximum Feret diameter: the longest distance between two hull points. Drawn from hull point a to hull point b (both on the outline).
- **Length direction** d = (b-a)/|b-a|; normal n.
- **Width (user's definition)** = Feret diameter perpendicular to the length: max - min of the hull projections on n (same half-cell convention as the length). `width_line` is the segment along n of that length, at the mean along-d position of the two extreme outline points; `width_caliper_px` equals `width_px`.
- **Mid-chord** (outline-to-outline run along n through the midpoint of the length line) was the earlier default and is kept as `width_chord_px`; the `standing` rule still uses it (L / chord W), so its threshold is unchanged.

## 5. Exclusion rules (each a test with a threshold, px at 300x)

Order of tests; first hit gives the reason.

| Reason | Test | Threshold |
|---|---|---|
| `small` | mask area | < 600 px (~ 25 um eq. diameter) |
| `not_particle` | mean grey of the 1-px rim minus local background (median filter 101 px) | < 8 grey levels (substrate blobs, charging regions, background masks) |
| `cut_off` | min distance of any mask pixel to the image edge or to the info-bar top (row 768) | < 3 px |
| `overlapped` | fraction of the mask outline within 3 px of another **particle** mask (neighbours exclude background masks: hole-filled area > 1.3 x area or > 20 % of image; and `not_particle` masks) | > 0.20 |
| `overlapped_shape` | solidity = area / convex-hull area | < 0.80 (occlusion junction, merged flakes, folded flakes) |
| `standing` | Feret L / chord W > 3.0, or interior (eroded 3 px) mean minus background > 50 grey | proposal only |

What can and cannot be detected:
- Cut-off: reliable.
- Overlap: contact between two separate SAM masks is reliable. A flake lying on top of another is **not** distinguishable from the one underneath: the user kept 300x_3 P2 (contact 0.154, partly covered by a neighbour) and 300x-31 P2 (contact 0.103). A 0.08 threshold drops both, so 0.20 is used. Stacked flakes that SAM returns as one mask are caught only through solidity.
- Standing: **no reliable cue on this data**. Edge-on flakes are bright and elongated (300x_3 #9: brightness 104, aspect 2.8; #10: 85, 3.0), but flat GT flakes also reach brightness 34 (300x_10 P2, 300x-31 P1), and tilt cannot be read from a 2-D outline. Threshold 25 drops 2 GT particles; 50 keeps all. Treat it as a proposal: auto-detect excludes only the obvious ones; the user removes the rest.

Results on 43 images (393 masks): small 40, not_particle 75, cut_off 34, overlapped 20, overlapped_shape 25, standing 23, **measure 179**.
- All 9 hand-measured particles survive the rules.
- Precision: in the 3 labelled images auto keeps 10 / 3 / 6 particles vs 2 / 3 / 4 hand-measured. The user measured a subset, so the extras are not necessarily wrong. 300x_3 extras include crowded flakes (#15, #17, #18) whose outlines touch neighbours below 20 %. The app must make removal one click.

## 6. Accuracy vs labels (px; % = (auto - GT) / GT)

| Image P | GT L | auto L | click L | GT W | auto W chord | click W chord | caliper W |
|---|---|---|---|---|---|---|---|
| 300x_3 P1 | 134.9 | +2.6 % | +2.6 % | 92.7 | +1.1 % | +2.2 % | +5.9 % |
| 300x_3 P2 | 297.1 | -0.5 % | -0.1 % | 189.6 | -0.1 % | -0.6 % | +1.2 % |
| 300x_10 P1 | 342.5 | +2.0 % | +2.1 % | 191.9 | -3.6 % | -3.9 % | +5.5 % |
| 300x_10 P2 | 117.3 | 0.0 % | +0.3 % | 82.5 | +3.0 % | +3.0 % | +5.0 % |
| 300x_10 P3 | 254.1 | -0.7 % | -0.7 % | 149.3 | +1.1 % | +1.1 % | +1.2 % |
| 300x-31 P1 | 127.4 | +1.5 % | +2.3 % | 52.0 | +12.0 % | +11.5 % | +62 % |
| 300x-31 P2 | 88.6 | +12.9 % | +12.9 % | 55.2 | +23.6 % | +23.6 % | +45 % |
| 300x-31 P3 | 213.2 | +2.1 % | +2.3 % | 99.5 | +18.3 % | +24.1 % | +51 % |
| 300x-31 P4 | 147.2 | -1.3 % | -1.3 % | 76.0 | +5.3 % | +5.3 % | +15 % |

- Length: 8 of 9 within +-2.6 % (<= 7 px). Failure: 300x-31 P2 +12.9 %; the user's line stops short of the mask's far corner.
- Width, capped-style labels (5 particles): chord within +-4 %; caliper +1..6 %.
- Width, 300x-31 caliper-style labels: auto is +5..24 % (chord). The user's tangent lines sit inside the visible outline (e.g. P3, D1: the top tangent line crosses the flake), and P3's hand length is not the maximum Feret (auto max Feret runs along the top edge, 218 vs 213 px, about 15 deg away). Two near-equal Feret directions make the width direction unstable. No outline-based rule reproduces these widths; they look like judgement (ignoring flaps or tilted edges).
- Overlays: `validation/particle-proto/sam16_<stem>.png` for the 3 labelled images (cyan = GT) and 300x-12, 300x-18, 300x-25, 300x_6, 300x-2. Green = measure (yellow L + chord W, magenta = caliper W), orange = overlapped, magenta = shape, blue = standing, red = cut-off, grey = not particle. `thr_*.png` = threshold method, `sam32_*.png` = pps 32.
- Recall gap seen: 300x-25 bright flake at ~(905, 530) got no mask at pps 16. It is probably standing anyway, but recall was not measured. Click-to-segment covers misses.

## 7. What stays manual

- Removing extra auto particles (precision is a user choice; see section 5).
- Standing / tilted flakes that pass the weak cue.
- Any particle where the user's judgement differs from the outline (300x-31 style). Use manual lines.
- Mode 3: the user draws the length and width lines; no mask needed.

## 8. Backend API contract

New module `scripts/particle_detect.py` (pure functions, no state):
- `feret_measure(mask) -> dict(length_px, length_line=[[x,y],[x,y]], width_px, width_line, width_caliper_px, solidity)` (code in `proto.py: feret, chord`).
- `particle_features(masks, gray) -> list[dict]` and `exclusion_reason(features) -> str|None` with the constants in section 5 at module top.
- `detect_particles(gray, proposals) -> (kept, excluded_counts)`; `proposals` = SAM automatic masks resolved as in `lab_workflow.py`.

LabEditor endpoints (`scripts/lab_editor.py`, add to the `do_POST` whitelist and dispatch):

1. `POST /api/detect-particles {dataset, revision}` -> runs SAM automatic masks on the analysis image (rows above the info bar), measures, applies the rules, adds every kept particle as a new object in **one** `self.save(...)` revision (one undo). Returns `{revision, object_ids: [...], excluded: {cut_off: n, overlapped: n, overlapped_shape: n, standing: n, not_particle: n, small: n}}`. Existing objects are kept; new masks are carved with `& ~occupied` like `add_tube`; a proposal covering an existing object by > 50 % is skipped.
2. `POST /api/measure-particle {dataset, revision, point: [x, y]}` -> SAM point prompt (reuse `quick_segment`'s predictor path / `Editor.preview`), highest-score mask, connected component under the click, `feret_measure`, add one object (one revision). The rules are **not** applied on a click (the user chose it); return the reason as `warning` if one would fire. Error "This particle is already measured as #N." when the click is inside an existing particle object.
3. `POST /api/particle-line {dataset, revision, axis: 'length'|'width', points: [[x,y],[x,y]], object_id?}` -> manual straight line. Without `object_id` a new object is created (empty-mask allowed or a 1-px line mask, as `add_tube` does for tubes); with it, the axis line of that object is replaced. Validate exactly like `manual_measurement` (finite, inside the image, distinct points). `measurement_methods[axis] = 'manual_line'`.

Annotation shape (per object, beside `tube`):
```json
"particle": {
  "length_line": [[417.1, 495.7], [708.9, 439.5]],
  "width_line":  [[568.4, 374.1], [599.6, 561.1]],
  "length_px": 297.1, "width_px": 189.6, "width_caliper_px": 191.9,
  "source": "auto" | "click" | "manual",
  "features": {"contact": 0.154, "solidity": 0.977, "aspect": 1.54, "rim": 17.0, "interior": 3.7}
}
```
`measurements()` / CSV rows: `length_um`, `width_um` from `*_px x um_per_pixel`.

Saved figures (`save_labels`): name(2) = length lines only, name(3) = width lines only; label text = value only, e.g. `269.33 µm` (no T#/D#). CSV `name(2).csv` / `name(3).csv` with `label` = object id. Extend the early return `if not any('tube' in a ...)` to `'tube' in a or 'particle' in a`.

Figure style: 1-px #ffff00 (`TUBE_COLOR`) straight line between the two outline points, plus end caps: 1-px line perpendicular to it, 9 px long, centred on each end (as in the examples). Text in #ffff00 placed by the existing `place_tube_labels` (it already keeps text off masks, lines, other labels and the border); pass the particle's own segments = the line + both caps, anchor = line midpoint.

## 9. Implementation notes for Sonnet

- Reuse: `lab_geometry.place_tube_labels`, `raster_segments`, `TUBE_COLOR`, `measured_overlay` (add a `particle` branch next to the `tube` branch); `lab_editor.add_tube` pattern (occupied carving, `self.save(...)`, history); `manual_measurement` validation; `quick_segment` / `pore_editor.Editor.preview` for the predictor; `segment_first_pass.ProgressGenerator` + the settings dict in `lab_workflow.py` for automatic masks (reuse `self.editor.predictor.model` when loaded; `points_per_batch=1` on Intel GPU).
- Do **not** reuse `lab_geometry.geometry()` for the width: its `width_pixels` is the minimum Feret over hull-edge normals, not the width perpendicular to the max Feret. Its `max_feret_pixels` / `feret_line` (rotating calipers + half-cell extension) is equivalent to the prototype length and may be reused; its `length_pixels` is the skeleton centerline, not the Feret.
- Info-bar bottom: do not use `detect_information_footer` as is on this data (returns 818, true 768). Either fix it (accept the first fully uniform row, std < 1, after textured rows) with a test on these images, or let the user's `analysis_bottom` decide.
- Tests (`tests/`): synthetic ellipse mask -> length = 2a +-1 px, chord width = 2b +-1 px, caliper = 2b; rectangle rotated 30 deg; L-shape -> solidity < 0.8; mask touching the bottom row -> `cut_off`; two masks sharing 30 % outline -> `overlapped`. One GT regression (300x_3 P2: L 297 +-3 %, W 190 +-4 %) only if the image is available in the test data.
- Keep CNT tube images on the existing Tube tool; the particle tool is a separate mode.

## 10. Risks and unverified points

1. **Width definition**: the user said "Feret perpendicular to the length", but the labels match the mid-chord (+-4 %), not the caliper (+1..6 %, up to +62 %). Default = mid-chord; confirm with the user.
2. **300x-31 widths are not reproducible** from the outline (+5..24 %); the labeller placed tangent lines inside the outline. Ask whether that image follows the same protocol.
3. **Standing detection has no reliable cue**; only obvious bright elongated flakes are caught. Accuracy of the standing rule is unmeasured (no labels of standing flakes).
4. **Overlap**: "on top of" vs "underneath" cannot be told apart; threshold 0.20 was set from 2 GT particles only.
5. **Precision**: auto keeps more particles than the user measured (19 vs 9 in the labelled images); not a correctness measure. Recall was not measured (one visible miss in 300x-25).
6. Footer detection returns the wrong row on 35 of 43 images.
7. Thresholds are in px for 300x; for other magnifications scale `MIN_AREA` by (um/px)^-2 or express them in um. Only 300x was checked.
8. Only 9 GT particles in 3 images; numbers are indicative, not statistics.
9. Prototype quirk: running SAM from a plain script with the Intel GPU worker re-executes the script's top level once in the worker (outputs printed twice); product entry points are guarded.
10. One run of `points_per_side=32` fell back to CPU after "GPU model loading exceeded 120 seconds"; the GPU timings above come from the pps-16 run and the click test.
