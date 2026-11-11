⚠️ DEGRADED: single-context (impeccable engine download failed, so `impeccable detect` did not run; reviewer was already a delegated sub-agent; no live app run)

# Report workspace UI review (impeccable audit + critique)

Date: 2026-11-09. Scope: `ui/report-ui.css`, the "Report workspace UI" block in `ui/labimage.js` (lines 357-647), `ui/editor.html`. Mode: **Operate** (an instrument UI where the user completes a measurement task).

Evidence used: source reading, and the 800 px captures `after-*.jpg` and `labeling-mode-unchanged.jpg` in the session scratchpad. Not used: the live app and the deterministic detector. Items marked *unverified* need one DevTools check before anyone fixes them.

## Fix status (2026-11-09)

| Item | Status | Note |
|---|---|---|
| P1-1 T/D persists | **Fixed** | `tube` flag added in `scripts/pore_editor.py` `measurements()` (the live `measurements` API; `analyze_candidates.py` is the export path and was not needed). `labimage.js` reads `r.tube`; `tubeIds` kept as fallback. Test: `tests/test_tube_flag.py`. Live: reload shows `T3 · D3 / SAM mask`. |
| P1-2 Measurements stale | **Fixed** | `tubeSchedule` now calls `renderMeasurements`. Live: count follows trace, undo, undo. |
| P1-3 Single-pane hero | **Fixed** | `report-ui.css` (Tube hides Original pane), `comparison.js` `fit()`, refit in `labStrip()`. Home-button "Compare" toggle (optional step 4) not added. |
| P1-4 Labeling Home button | **Skipped** | Owner has not approved a Labeling change. |
| P2-1 Nest `result.tube` | **Skipped** | Needs `lab_editor.py` response shape / `cnt_detect` tests; another agent is editing them. `tubeResponse` shim stays. |
| P2-2 Chrome rows | **Fixed** | Document bar `nowrap` with ellipsis name (title already set in `workspace.js`); strip keys `nowrap`, keys 4+ and Korean step text hidden under 1400 px. Wrap restored under 1000 px. |
| P2-3 Pore panels in Tube | **Fixed** | Legend and the `.metric` Measurements panel hidden in Tube mode. |
| P2-4 Calibration chip | **Fixed** | `#tubeCalib` shown when unit is `px`; opens the Scale step. Not exercised live (test dataset is calibrated); logic only. |
| P2-5 Recovery error | **Fixed (client-side)** | Client appends "Select it in the list or delete it, then trace again." to "already measured." The overlapping object id is not named, because that needs the `lab_editor.py` change. |
| P2-6 Korean labels | **Fixed** | Step chips, Tubes heading, empty-state title. |
| P2-7 Collapsible semantics | **Fixed** | Real `<button class="ph-toggle">` inside the `<h2>`; `aria-expanded` on the button. |
| P2-8 Grey step-1 tab | **Not reproduced** | Computed background settles to transparent. The grey box is a frozen 120 ms `background` transition in a captured frame. |
| P3-1 ID repeated | **Fixed** | ID cell `T3 · D3` or `#3`; tags removed from value cells; heads `T · Length`, `D · Width` when the list holds tubes. Heads wrap to two lines so the table fits 344 px. |
| P3-2 Mean ± SD | **Fixed** | Sample SD for n>=2, mean only for n=1. |
| P3-3 Reduced motion | **Fixed** | Static highlight on `tr.fresh`. Not exercised live. |
| P3-4 Double announce | **Fixed** | `role="status"` removed from `#tubeStatus`. |
| P3-5 Hard-coded colours | **Fixed** | Tokens `--line-3 --ink-5 --stop --bad-ink --close`; JS reads `--trace` via `traceColor()`. |
| P3-6 Add looks pressed | **Not reproduced** | `aria-pressed="false"` and transparent background live in Tube mode; same stale-transition capture artefact. |

## Scores

### Audit health (technical)

| # | Dimension | Score | Key finding |
|---|-----------|-------|-------------|
| 1 | Accessibility | 3 | Contrast passes everywhere (`--text-3` on `--ink-2` = 5.7:1). Problems: `role=button` on `<h2>`, 9.5 px shortcut chips, and `aria-selected` on plain table rows. |
| 2 | Performance | 3 | `pointermove` is throttled with rAF. `tubeSchedule` fetches a snapshot and then drops half of it (see P1-2). |
| 3 | Theming | 3 | The token system is clean. Some colours are still hard-coded: `#4b5562`, `#3d4652`, `#c2410c`, `#9b2f2f`, `#ffd3d3`. `TUBE_STYLE.color` duplicates `--trace` in JS. |
| 4 | Responsive | 3 | The 1000 px breakpoint works. At 1280 px the document bar and the hint strip wrap to two lines and take height from the image. |
| 5 | Implementation integrity | 3 | Coherent and product-specific. Two data bugs: the T/D prefix is lost, and the Measurements panel goes stale. |
| **Total** | | **15/20** | **Good**: fix the weak spots, no overhaul needed |

### Design health (Nielsen)

| # | Heuristic | Score | Key issue |
|---|-----------|-------|-----------|
| 1 | Visibility of system status | 2 | The Measurements panel shows stale counts after a tube is measured. Lengths in px carry no "not calibrated" warning. |
| 2 | Match system / real world | 3 | T#/D# match the figure labels, but only for the current session. |
| 3 | User control and freedom | 3 | Undo works from Esc, Backspace, Ctrl+Z, the rail and the panel. |
| 4 | Consistency and standards | 2 | T/D in the list turn into L/W after a reload. Korean appears only in the hint text. "Undo" exists in 3 places. |
| 5 | Error prevention | 3 | The backend rejects duplicate tubes and caps a trace at 20 points. |
| 6 | Recognition rather than recall | 3 | The hint strip shows the step and the keys for the active tool. |
| 7 | Flexibility and efficiency | 3 | Single-key tools, and Ctrl-click falls back to SAM. |
| 8 | Aesthetic and minimalist design | 2 | The image is not the hero: two half-width panes with black below them, an irrelevant legend row, diameter metrics, and the ID repeated three times. |
| 9 | Error recovery | 2 | "This tube is already measured." gives no next step. |
| 10 | Help and documentation | 3 | Inline hints, step chips and the empty state carry the teaching. |
| **Total** | | **26/40** | **Good, not yet a confident instrument readout** |

### Verdict

**Design specificity: pass.** The dark graphite chrome, the measurement yellow that matches the overlay, the cyan reserved for the live trace, the step strip and the T#/D# tags make a world authored for SEM tube measurement. It is not a generic dashboard skin.

The biggest gap is the stated intent "image is the hero". At 1280 px the SEM image fills about 45 % of the window. The rest is a duplicate Original pane, black letterbox, and three rows of chrome above the image.

## Known items (confirm or reject)

| Item | Verdict | Evidence |
|---|---|---|
| Labeling Home button white-on-white | **Confirmed** (pre-existing) | `ui/labimage.css:2` sets `#labHomeButton{color:#f4f8fc;background:transparent}` on the white labeling header. Contrast is 1.07:1. Visible in `labeling-mode-unchanged.jpg` as an empty white box at the top right. |
| T/D prefix reverts to L/W after reload for SAM tubes | **Confirmed** | `labimage.js:594` decides `isTube` from `source==='cnt_trace'\|\|tubeIds.has(id)`. `tubeIds` is a session-only Set, cleared at `labimage.js:632`. `measure_tube` (`scripts/lab_editor.py:161`) keeps the SAM `source` (`prompted_sam`) and adds only the `tube` annotation. The figure tests `'tube' in annotation` (`scripts/lab_geometry.py:297`), so the image shows T3/D3 while the list shows L/W. |
| Measurements panel stale until refresh | **Confirmed** | `tubeSchedule` (`labimage.js:625-631`) fetches `measurementSnapshot()` and passes it only to `tubeRender`, so the Tubes list refreshes but `#count`/`#fraction`/histogram do not. `accept()` (`editor.html:151-152`) then shows "Objects changed. Click ↻ to update." (visible in `after-editor-tube-live-trace-1280.jpg`: Object count 1 next to a list of 2). |
| Tube `width` key clashes with image `width` | **Confirmed** | `tube_values` (`scripts/lab_editor.py:124-128`) returns `width`. `result.update(**tube_values)` at `lab_editor.py:151` and `:164` overwrites the image `width` in the server reply. The client patches it back via `tubeResponse` (`labimage.js:512`). |

## Findings

### P0: blocking

None. Every flow completes.

### P1: major

**P1-1. T/D prefix lost after reload; list and figure disagree**
- Location: `ui/labimage.js:594`; `scripts/lab_fast_labels.py:100` (candidate dict); `scripts/analyze_candidates.py:152` (measurements table).
- Problem: SAM-measured tubes are listed as L/W after a reload while the figure labels them T#/D#. Users cross-reference the table and the figure by these tags.
- Fix:
  1. In `scripts/analyze_candidates.py`, after line 152 (`table["source"] = ...`), add:
     `table["tube"] = table["candidate_id"].map(lambda i: "tube" in notes.get(str(i), {}))`.
     This is the data `measurementSnapshot()` returns.
  2. In `labimage.js:594`, replace `r.source==='cnt_trace'||tubeIds.has(r.candidate_id)` with `r.tube||tubeIds.has(r.candidate_id)`. Keep `tubeIds` as a fallback for a stale backend.
  3. Change the `src` label on the same line to `r.source==='cnt_trace'?'Ridge trace':r.tube?'SAM mask':'Manual path'`.
  4. Add one test asserting that `tube` is True for a `measure-tube` object after reload.
- Principle: Consistency and standards (#4); Match between system and real world (#2).

**P1-2. Measurements panel stale after every tube, undo or delete**
- Location: `ui/labimage.js:625-631` (`tubeSchedule`).
- Problem: the "instrument readout" shows a wrong object count until the user clicks ↻. The data was already fetched and then thrown away.
- Fix: in `tubeSchedule`, replace `tubeKey=data.dataset+':'+data.revision;tubeRender(data)` with `renderMeasurements(data)`. The override at `:620-622` already sets `tubeKey` and calls `tubeRender`, and the base clears `#measurementStatus`. With the snapshot fetched there, the explicit `renderMeasurements(await measurementSnapshot())` calls in `tubeRun`/`tubeSam` (`:518`, `:532`) become redundant: either leave them (harmless) or drop them to save one request.
- Principle: Visibility of system status (#1).

**P1-3. Image is not the hero: two half-width panes plus letterbox**
- Location: `.comparison-viewports` (`workspace.css:17`, grid 1fr 1fr); `report-ui.css:102,157`; `comparison.js:133-137` (`fit`).
- Problem: in Tube mode the user measures only on the Segmentation pane. The Original pane halves the image size and also draws a mirrored red crosshair, a second focus point. A 4:3 SEM image fitted to half the width leaves about 40 % of the well black (all 1280 captures).
- Fix (report mode only):
  1. In `report-ui.css`, inside the body block, add:
     `&[data-tool=tube] .comparison-viewports{grid-template-columns:minmax(0,1fr)}`
     `&[data-tool=tube] .comparison-pane:first-child{display:none}`
  2. In `comparison.js` `fit()`, make the hidden pane not count. Replace `Math.min(left.clientWidth,right.clientWidth)` with `Math.min(left.clientWidth||Infinity,right.clientWidth)`, and the same for `clientHeight`.
  3. In `labStrip()` (`labimage.js:434`), after setting `document.body.dataset.tool`, call `window.resizeComparison?.()` so the image refits when the tool changes. Otherwise a hidden pane leaves the zoom at the clamped 10 %.
  4. Optional: add a "Compare" toggle button in `.document-toolbar` that removes the override for users who want the original.
- Principle: Aesthetic and minimalist design (#8); brief "image is the hero".

**P1-4. Labeling Home button invisible (pre-existing, outside the Report scope)**
- Location: `ui/labimage.css:2`.
- Problem: white text on a white header (1.07:1). Labeling users have no visible way back to the mode chooser. This fails WCAG 1.4.3 and 1.4.11.
- Fix: append to `labimage.css`:
  `body[data-lab-mode="labeling"] #labHomeButton{color:#334155;border-color:#cbd5e1}`.
  Report mode keeps its own rule at `report-ui.css:58`. This touches the Labeling look, so it needs the owner's OK, because the brief says Labeling stays untouched.
- Principle: Accessibility (contrast); Visibility of system status (#1).

### P2: minor

**P2-1. Backend `width` key collision**
- Location: `scripts/lab_editor.py:124-128,151,164`; `ui/labimage.js:510-512,518,532`.
- Problem: the API reply carries the wrong image `width`. Every future consumer must remember the client shim.
- Fix: nest the tube values instead of spreading them.
  1. In `trace_tube`, change line 151 to `result.update(object_id=identifier, tube=self.tube_values(state, c))`.
  2. In `measure_tube`, change line 164 to `result['tube'] = self.tube_values(state, c)`.
  3. In the client, delete `tubeResponse` (`:512`). Call `accept(result)` directly. Change `tubeSummary(result)` to `tubeSummary(result.tube)` at `:519` and `:533`.
  4. Update any test that reads `result['length']`/`['width']`: grep `tests/` for `length_px`, `'width'`. Coordinate with the agent editing tests.
- Principle: Implementation integrity (no shims that hide a data defect).

**P2-2. Chrome rows steal height from the image at 1280 px**
- Location: `report-ui.css:111-120` (document bar), `:136-151` (hint strip).
- Problem: the `IDs` checkbox wraps to its own row (`after-editor-tube-*.jpg`), and the strip's key list wraps under the steps. That leaves 3-4 chrome rows above the image.
- Fix:
  - In the document bar, set `& .document-toolbar{flex-wrap:nowrap}` and `& #editorImageName{flex:1 1 0;min-width:0;max-width:none;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}`. Add a `title` with the full name in JS (`$('editorImageName').title=...` where the name is set).
  - In the strip, set `& #toolStrip .ts-keys{flex-wrap:nowrap;overflow:hidden}` and hide the lowest-value keys under 1400 px: `@media(max-width:1400px){body[data-lab-mode="report"] #toolStrip .ts-keys span:nth-child(n+4){display:none}}`. The panel hint and the rail tooltips still carry them.
- Principle: Aesthetic and minimalist design (#8).

**P2-3. Pore-centric panels compete with the Tubes readout**
- Location: `report-ui.css:178` (Measurements panel `:has(.metric)`), `:103` (legend), `labimage.js` (inspector order).
- Problem: in Tube mode the inspector shows Area fraction, Median diameter, Boundary objects and a Diameter Distribution histogram. These are mask metrics that do not apply to CNT length/width. The legend "Objects · Added · Preview · Replaced objects" also has no meaning for traces. Both dilute the one readout that matters.
- Fix: add
  `&[data-tool=tube] :is(.legend,#editorPanel>aside>.panel:has(.metric)){display:none}`
  next to the existing rule at `report-ui.css:108`. Keep them for the Add/Box tools.
- Principle: Aesthetic and minimalist design (#8); Recognition rather than recall (#6).

**P2-4. Uncalibrated lengths shown as plain px**
- Location: `labimage.js:463` (Tubes panel head), `:588` (`tubeRender`).
- Problem: a measurement tool silently reporting px invites "px" values pasted into a report as µm-scale results. Step 2 is labelled "optional".
- Fix: in `tubeRender`, when `unit==='px'`, show a chip after the count:
  `<button class="sm" id="tubeCalib">Not calibrated · Set scale / 스케일 설정</button>`.
  Its `onclick` opens the Scale step (`document.querySelector('[data-panel=setup]').click()`). Style it as `&#tubeCalib{color:var(--warn);border-color:rgba(255,184,107,.45);background:transparent}`. Hide it when a unit is set.
- Principle: Visibility of system status (#1); Error prevention (#5).

**P2-5. Error message without a recovery path**
- Location: `scripts/lab_editor.py:142` ("This tube is already measured."); `labimage.js:640-645`.
- Problem: the user does not know which object overlaps or what to do.
- Fix:
  1. In `trace_tube`, find the overlapping object: `hit = max(state['masks'], key=lambda i: (state['masks'][i] & tube_mask(...)).sum())`.
  2. Raise `ValueError(f'This tube overlaps #{hit}, already measured. Select #{hit} in the list or delete it, then trace again.')`.
  3. In the client, nothing else changes.
- Principle: Help users recognize, diagnose and recover from errors (#9).

**P2-6. Bilingual labelling is inconsistent**
- Location: `labimage.js:363-388` (`TOOL_UI`), `:432` (strip steps), `:465` (empty state).
- Problem: the brief asks for Korean + English labels. Today Korean appears only in the Tube tooltip and one hint line. The step chips, the empty state and the error message are English only.
- Fix: add a Korean secondary line in the same pattern as the hint (`<span lang="ko">`):
  - strip steps: `한쪽 끝 클릭` / `Shift-클릭으로 굴곡` / `반대쪽 끝 클릭`, as `<small lang="ko">` inside each `li`, styled `color:var(--text-3)`;
  - empty-state title: `아직 측정한 튜브가 없습니다`;
  - Tubes h2: `Tubes · 튜브`.
  Keep one convention: English first, Korean second, Korean in `--text-3`.
- Principle: Consistency and standards (#4).

**P2-7. Collapsible headers lose heading semantics**
- Location: `labimage.js:450-458` (`labCollapsible`).
- Problem: `role="button"` on `<h2>` removes the heading from the screen-reader outline.
- Fix: wrap the heading text in a real button instead: `h.innerHTML=`<button type="button" class="ph-toggle" aria-expanded="...">${h.textContent}</button>``. Toggle `aria-expanded` on that button and drop `tabIndex`, `role` and `onkeydown` from the h2. Style it as `& .ph-toggle{all:unset;display:flex;justify-content:space-between;width:100%;cursor:pointer}` and move the chevron `::after` onto `.ph-toggle`.
- Principle: Accessibility (semantic HTML, WCAG 1.3.1).

**P2-8. Step 1 tab shows a light-grey box with near-invisible text (unverified)**
- Location: `.steps [data-panel=load]`, top-left of every 1280 capture.
- Problem: in report mode "1 Load Image" renders on a light background (`after-editor-empty-1280.jpg`). No rule in the three stylesheets produces a light background in report mode, so this may be a capture artefact (pointer resting there) or a stray state class.
- Fix: in DevTools, inspect the computed `background-color` of `[data-panel=load]` in report mode.
  - If it comes from `workspace.css:129 button:hover` or `:14 .steps .active`, add `& .steps button:not(.active){background:transparent}` to `report-ui.css` after line 60.
  - If it was the capture pointer, drop this item.
- Principle: Consistency and standards (#4).

### P3: polish

**P3-1. ID repeated three times per row**
- Location: `labimage.js:597`.
- Problem: `#3`, `T3` and `D3` all appear in one row and squeeze the numeric columns.
- Fix: in the ID cell show `T3 · D3` (tube) or `#3` (other). Remove the `.tag` spans from the value cells. Move the tag letter into the column heads: `T · Length (µm)`, `D · Width (µm)`.

**P3-2. Mean row lacks spread**
- Location: `labimage.js:604-606`.
- Problem: an instrument readout should show variability.
- Fix: render `mean ± sd` with `sd = sqrt(Σ(v-mean)²/(n-1))` when n≥2, and `--` otherwise.

**P3-3. Reduced-motion global kill removes the fresh-row cue**
- Location: `report-ui.css:293-295`.
- Problem: under reduced motion the new-row cue disappears entirely.
- Fix: keep the kill, then add `body[data-lab-mode="report"] .results tbody tr.fresh{background:rgba(255,216,74,.18)}` inside the media query. That gives a static highlight in place of the flash. The class is cleared on the next render.

**P3-4. Error announced twice**
- Location: `labimage.js:640-645`.
- Problem: the same error goes into both `#status` and `#tubeStatus`, two live regions, so screen readers announce it twice.
- Fix: remove `role="status"` from `#tubeStatus` (`labimage.js:464`). It stays visible as text.

**P3-5. Hard-coded colours outside tokens**
- Location: `report-ui.css:29,50,88,164,238`; `labimage.js:384,568-579`.
- Fix:
  - Add `--line-3:#4b5562;--ink-5:#3d4652;--stop:#c2410c;--bad-ink:#ffd3d3` and use them.
  - In JS, read `getComputedStyle(document.body).getPropertyValue('--trace')` once into `TUBE_STYLE.color`.

**P3-6. "Add" looks pressed while Tube is active (unverified)**
- Location: the rail in `after-editor-final-1280.jpg` and `after-editor-narrow-900.jpg`.
- Problem: this is probably the hover style under a resting pointer.
- Fix: confirm `aria-pressed="false"` on `[data-mode=positive]` live. Drop this item if it was hover.

## What works (keep)

- **Token discipline and contrast.** Every text token passes AA on every surface (lowest is `--text-3` on `--ink-3`, 5.1:1). Yellow is reserved for measurements and cyan for the live trace, so colour carries meaning.
- **Tube step strip.** The `now`/`done` chips, the point count and context keys teach the 3-click flow without a modal. The live trace's dark halo, dashed rubber band and numbered points read well on bright SEM texture.
- **Keyboard and undo model.** The rail order matches the visual order for Tab. Undo has a single ladder: pending point, then input, then saved edit. `aria-keyshortcuts` and `aria-pressed` are set. Labeling is restored by `labRailOrder(false)`.

## Recommended actions

1. **[P1]** `/impeccable harden`: T/D flag from the backend (P1-1), Measurements refresh (P1-2), `width` key nesting (P2-1).
2. **[P1]** `/impeccable layout`: single-pane hero in Tube mode (P1-3), chrome row wrap (P2-2), hide pore panels in Tube mode (P2-3).
3. **[P1]** `/impeccable audit` on Labeling after the owner approves the Home button fix (P1-4).
4. **[P2]** `/impeccable clarify`: calibration chip (P2-4), recovery error (P2-5), Korean labels (P2-6).
5. **[P2]** `/impeccable polish`: collapsible semantics, step tab check, P3 items.

Re-run `/impeccable audit` after the fixes. The run needs the engine downloadable so the detector runs.
