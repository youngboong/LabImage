# CNT auto-measurement plan (Report workspace)

Goal: in the Report workspace, click (or auto-detect) a carbon nanotube and get a yellow centerline curve with its length (T#) and a width mark (D#) like the user's `X(2).tif` / `X(3).tif` annotations. Phase 1 scope: "certain" tubes only — clearly visible start and end, not touching the image border, not fused into a tangle. The 1kx–3kx images (isolated tubes 15–60 px wide on a dark background) are the target; 100x–500x agglomerate images are out of scope for automatic detection (user can still measure them with the existing endpoint tools).

Principles: reuse the existing mask + `annotations[id].manual_measurements` data model so overlay, CSV/JSON export and the report generator keep working unchanged; add one backend module and two endpoints; keep UI changes minimal (the full redesign is a separate step).

---

## 1. Workflow and UX

1. Load image → Report mode → calibrate as today (scale bar label typed by the user; `lab_footer` + `detect_scale_bar` already give the bar pixel length). Open the segmentation workspace.
2. New button **Find tubes** (Report mode only). Backend runs the detector on the analysis ROI (above the footer) and returns N candidates, each with: `centerline` (polyline, image px), `length_px`, `width_px`, `width_line` (two endpoints), `confidence`, `flags` (`border`, `branched`, `short`, `low_contrast`). Only candidates with no flags are shown by default; a "Show rejected" toggle reveals the rest in grey.
3. Candidate overlay: dashed yellow centerline per candidate with a small index badge. Click toggles selection (selected = solid yellow). "Select all certain" / "Clear". Hovering shows length/width in the status bar.
4. **Add selected** → one request. Each selected candidate becomes an object: mask = tube band (see §3), `manual_measurements.length` = centerline, `manual_measurements.width` = width line, methods `auto_centerline` / `auto_width`. Objects get normal IDs; the overlay (`measured_overlay`) already draws yellow paths, end caps and outside labels.
5. Click-to-measure fallback (the user's original ask): existing Add (A) point click on a tube that the detector missed → `quick_segment` as today, then automatically run the same centerline + width routine on the SAM mask and save it as the length/width measurement (no manual endpoints). Keep the existing endpoint/draw tools for corrections.
6. Corrections: existing Delete, Ctrl+Z, and the endpoint tools (re-saving an axis overwrites the automatic one). Clear saved measurements already resets both axes.
7. Labels: `measured_overlay` currently prints `151.12 µm`; add the prefix `T{id}=` for length and `D{id}=` for width to match the user's style (one f-string change, behind the existing `show_ids` option or a new `label_style` figure option). Export (Save Images → `measurements.png/.csv/.json`, report PDF/HWPX/DOCX) needs no change because it reads the same annotations through `report_geometry`.

## 2. Detection approach

Options considered:

| Option | Pros | Cons |
|---|---|---|
| A. SAM2 automatic mask generator (existing labeling run, `LabWorkflow.run`) | already wired, GPU path exists | SAM proposals on thin curvy tubes are blobby, split long tubes into pieces, merge touching tubes; 16–32 pts/side costs minutes on CPU for 1024×946; masks still need a centerline step afterwards |
| B. Ridge/tubeness filter (skimage `sato`/`frangi`, bright ridges) → threshold → skeleton → graph tracing | geometry-native: gives centerline and local scale directly; ~0.7 s on CPU for the ROI at 4 sigmas (probed on `CNT_powder_1kx-12`); no model, deterministic | responds to every bright fibre including tangles and bundle edges → needs pruning/graph rules; width from the ridge mask is approximate |
| C. Hybrid: B for candidates + centerline, SAM point prompts along the centerline (existing `quick_segment`) for the mask/width when the user accepts | better masks | 1 SAM call per tube (≈1–3 s CPU each), more code |

Recommendation: **B**, with C deferred. The user's labels are polylines and a width at one station — exactly what a skeleton graph gives. SAM adds cost and no accuracy on the centerline. Width from the local ridge-mask half-width (distance transform) is adequate for 15–60 px wide tubes; revisit with C only if the width error in §5 is unacceptable.

Pipeline (new module `scripts/cnt_detect.py`):

1. `gray = normalized ROI` (above `analysis_bottom`). Optional 3×3 median to tame SE noise.
2. Ridge response `R = sato(gray, sigmas=σ, black_ridges=False)` with σ chosen from the calibration: tube radii expected 1.5–15 µm → σ = radius/px over 4–6 log-spaced values; store `argmax σ` per pixel as the local radius estimate. Uncalibrated images use σ = [2,3,5,8,12].
3. Mask `M = R > t` (Otsu over nonzero response, floored; expose as "Sensitivity" slider later if needed), remove components < ~300 px, fill holes.
4. Skeleton `S = skeletonize(M)`; build the pixel graph (reuse the sparse-graph code pattern in `lab_geometry.geometry`); collapse to a node/edge graph (junctions = degree ≥3, tips = degree 1); prune spurs shorter than 2× local radius; merge two collinear edges at a junction when the turning angle < 30°, so a tube crossing another is traced straight through.
5. Each remaining maximal chain with two tip ends is a candidate. Compute flags:
   - `border`: any mask pixel of the candidate within 2 px of the ROI edge (left/right/top or `analysis_bottom`).
   - `branched`: the chain retains a junction whose other branches are longer than 3× local radius (tangle/bundle).
   - `short`: length < 5× median width or < 40 px.
   - `low_contrast`: mean `R` along the chain below the image-level median of accepted chains × 0.5.
   - `confidence` = normalized mean ridge response × straight-through fraction; used only for sort order.
6. Return candidates sorted by length. Runtime budget: < 3 s CPU per image; no GPU needed.

"Certain" object = no flags. Rejected candidates stay available behind the toggle so the user can still accept them.

## 3. Centerline, length and width

Centerline (also used for the click-to-measure fallback on a SAM mask):

1. Skeleton path end-to-end: for a detector candidate the chain from §2; for a SAM mask, `lab_geometry.geometry(mask)` already yields the longest skeleton path (MST diameter) — reuse it.
2. Smooth: resample to 1 px arc spacing, then Savitzky–Golay or a moving average over ~2× local radius (removes the pixel staircase that inflates length by 3–8 %). Keep at most ~1 vertex per 3 px in the saved polyline (the user's labels are coarse polylines; ours may be finer).
3. End extension: skeletonize stops short of the tip by roughly one radius. Extend each end along the final tangent until the ridge mask (or SAM mask) ends — same ray-march as in `geometry`'s boundary extension, reused.
4. Length = sum of segment lengths × `um_per_pixel` (`manual_geometry` already does this for `manual_measurements.length`).

Width (the user's labels show one measurement at a chosen station, drawn as two parallel lines across the tube with a cross marker):

1. Stations: sample the centerline at 20 %, 35 %, 50 %, 65 %, 80 % of arc length, away from both ends.
2. At each station, take the perpendicular intensity profile (±3× local radius, bilinear sampling). Width = FWHM of the profile above the local background (median of the profile's outer quarter). Fall back to 2× distance-transform value of the tube mask when the profile has no clean peak.
3. Report the median of the five station widths; the saved `width_line` is the perpendicular segment at the station whose width is closest to that median, so the yellow mark sits on a representative spot. `measured_overlay` already draws the end caps (which produces the "two parallel lines" look).
4. Store `width_stations` (all five values) in the annotation for the evaluation and for a later per-station display; `width_pixels` stays the single number the table shows.

Mask for the object (needed because every object in `state['masks']` is a boolean mask): the ridge-mask component clipped to a band of ±(local radius + 1 px) around the centerline. Overlapping tubes may share pixels; the Report workspace tolerates overlaps (`shared` is tracked in `measure_masks`), so do not run the exclusive-overlap cleanup on these.

## 4. Where it plugs in

Backend:

- New `scripts/cnt_detect.py`: `detect_tubes(gray, um_per_pixel, analysis_bottom) -> list[candidate]`, `tube_measurement(mask_or_candidate, gray) -> dict(length_path, width_line, width_stations, length_px, width_px, flags)`. Pure numpy/scipy/skimage/cv2 (all already installed; skimage 0.26, scipy 1.17, cv2 5.0).
- `scripts/lab_editor.py`:
  - `LabEditor.detect_tubes(state, payload)`: runs the detector, caches the candidate list in `state['tube_candidates']` keyed by revision, returns candidates with polylines (no masks over the wire).
  - `LabEditor.add_tubes(state, payload)`: `payload.candidate_indices` → builds masks and annotations, one `self.save(...)` with action `dict(type='add-tubes', ...)`. Annotation per object: `dict(source='cnt_ridge_detector', supplemental=True, review_status='user_accepted', manual_measurements={'length': path, 'width': width_line}, measurement_methods={'length': 'auto_centerline', 'width': 'auto_width'}, width_stations=[...], detector_flags=[...], confidence=...)`.
  - `quick_segment`: after an instant apply in Report mode, call `tube_measurement` on the new mask and write the same two measurement entries (behind a `payload.get('auto_measure', True)` so the labeling mode and old tests are unaffected).
  - `make_handler.do_POST`: add `/api/detect-tubes` and `/api/add-tubes` to the tuple on line 173 and the dispatch below it; same host/origin checks.
- `scripts/lab_geometry.py`:
  - `report_geometry` re-routes only `object_path`/`object_path_via_center` through `center_connected_path`; the new methods fall through to `manual_geometry` unchanged. No edit needed except the `T{id}=`/`D{id}=` label prefix in `measured_overlay` (and skipping the automatic center dot when both axes are automatic).
- `scripts/lab_export.py`: nothing. `measurements.json.measurement_paths[id].methods` already records the method strings; add `width_stations` and `detector_flags` to that dict (two keys) so exports carry provenance.
- `scripts/analyze_candidates.measure_masks`: nothing; `report_geometry` supplies length/width.

UI (`ui/labimage.js`, Report-only panel next to the existing `manualPanel`):

- Panel "Tubes": buttons Find tubes, Select all certain, Clear, Add selected; checkbox Show rejected; status line with counts.
- Candidate overlay drawn in `labLayer` from the cached candidate list (dashed polylines, index badges, hit-test by distance to polyline ≤ 6 px for click-toggle). Clear the overlay on `onEditorAccepted` when the revision changes.
- No change to `editor.html`; the panel is injected like `manualPanel`.

Data model summary: no new files or tables. Everything lives in `annotations[id]` next to the existing keys, so revisions, Ctrl+Z (`snapshot`), export and reports work as they do now.

Tests (`tests/`): `test_cnt_detect.py` with synthetic images — one straight tube, one S-curve, one crossing pair, one border-touching tube — asserting length within 2 % and width within 10 % of the drawn values, and the correct flags. Reuse the style of `test_manual_paths.py`.

## 5. Evaluation against the user's labels

Data: `CNT/261103` (41 base images) and `CNT/261105` (13), each with `X(2).tif` (lengths) and `X(3).tif` (widths). Footer detection works on 48/54 base images (`detect_information_footer` → 768, bar 147–331 px); 6 images (`1kx-13`, `1kx-16`, `1kx-24`, `2kx-10`, `300x-35`, and one more) have a different footer layout (detected at 818, no bar) and need a hand-entered scale.

Script `scripts/cnt_eval.py` (dev-only, not shipped):

1. Scale: `um_per_pixel = label_um / bar_px`. Label values are not OCR'd; keep a small JSON table `{magnification: label_um}` filled by eye once (e.g. 1kx → 50 µm, 500x → 100 µm, 200x → 200 µm, 100x → 500 µm). Cross-check against the FoV text (e.g. 279 µm / 1024 px = 0.272 µm/px matches 50/183 = 0.273).
2. GT extraction from `(2)`: yellow = `R>150 & G>150 & B<100 & |rgb − gray| > 30` (verified: 3062 pure `#FFFF00` px plus anti-aliased fringe). 8-connected components; components with bounding-box extent ≥ 25 px and fill ratio < 0.15 are polylines (the text glyphs are < 25 px). Skeletonize each polyline component, order the pixels tip to tip, length = polyline arc length in px. Note the user's polylines are coarse chords through the tube, so GT length is a slight underestimate of the true arc; treat ±3 % as noise.
3. GT extraction from `(3)`: the same yellow mask; each width mark is two short parallel segments (36–70 px long, fill ratio 0.04–0.5 bounding boxes) 15–60 px apart plus a cross. Pair segments by parallel orientation and proximity; width = perpendicular distance between the two lines; location = midpoint. The label text gives the value for a sanity check only.
4. Matching: predicted centerline ↔ GT polyline when the mean nearest-point distance (both directions) ≤ 1.5× local tube radius and ≥ 70 % of GT arc length is covered. Width marks match the predicted tube whose centerline passes within one radius of the mark midpoint.
5. Metrics per image and pooled:
   - Detection recall on GT tubes (all GT, and the "certain" subset: GT tubes whose mask does not touch the border and that the detector would not flag `branched` — report both so the scope choice is visible).
   - False candidates per image among unflagged candidates.
   - Length relative error (median, 90th percentile) on matched tubes; signed bias to detect the staircase/extension issues.
   - Width relative error at the user's station: compare our profile width measured at the GT mark location (not our chosen station) so the metric isolates the width method; also report the error of our reported median width versus the GT value.
6. Output: `outputs/cnt_eval/<date>/summary.csv` plus per-image overlays (GT yellow, prediction cyan) for visual review.

Acceptance target for phase 1 (to be agreed): recall ≥ 80 % on certain GT tubes at 1kx–3kx, length median error ≤ 5 %, width median error ≤ 15 %.

## 6. Risks and open questions

Risks:

- Tangles and bundles (most of the 100x–500x images, parts of 1kx) will produce many flagged candidates; the user will still measure those by hand. Expect lower recall there by design.
- Ridge threshold sensitivity across images (brightness varies); may need the per-image Otsu plus an exposed slider.
- Width from one station is noisy on frayed/flattened bundles; the user's own choice of station is subjective, so width agreement may be limited to ~15–20 %.
- Overlapping tube masks share pixels; `exclusive_existing`/overlap cleanup must not run on them, and the labeling-mode instance export stays separate.
- Footer layout differs on 6 images; scale must be entered manually there (existing calibration flow handles it).
- Long polylines with many vertices increase `measurements.json` size slightly; keep ~1 vertex per 3 px.

Open questions for the user:

1. Width: one value at a representative station (matches your D# marks) or the median of several stations? Should the yellow mark be placed at mid-length or at the widest/cleanest spot?
2. Should the label text read `T1=151.12 µm` / `D1=4.23 µm` with per-axis counters as in your images, or keep the object ID (`#3`) with both values?
3. Phase 1 scope: 1kx–3kx isolated tubes only? Are the 100x–500x straight-line labels on bundles a separate "bundle length" feature?
4. For the clicked-object fallback, is SAM's mask acceptable as the tube footprint, or should the click only seed the ridge tracer (faster, no SAM)?
5. Scale label: keep manual entry, or add OCR of the footer FoV/scale text (new dependency)?
6. Are overlapping tubes allowed to share pixels in the saved masks (needed when two tubes cross)?
