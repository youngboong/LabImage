# LabImage UI review 2 (light "Bench instrument" redesign)

Date: 2026-11-09. Review only. No project file was edited except this one.

**Fix pass (2026-11-09):** all P1 and P2 items fixed, P3-1 fixed, P3-2 and P3-3 skipped. Each finding carries a status line. New screenshots: `scratchpad/ui3/`.

**Method:** DEGRADED, single context. The impeccable launcher could not download engine 0.1.19, so `impeccable context` and `impeccable detect` did not run. I applied the audit.md and critique.md rubrics by hand. I ran them in one context, not as two isolated sub-agents. I did not start a server or attach to the app, because the exe was being built. The evidence is the 24 screenshots in `scratchpad/ui2/` plus a source read of `ui/*.css`, `ui/*.js`, `ui/editor.html` and the export scripts they call.

**Screenshot freshness:** several screenshots predate the final polish pass. I checked these defects against the source and they are already fixed, so they are not listed below. Recapture these screenshots before the next review:
- "1 images" (screenshots 11 and 13)
- "Add Table" in Title Case (14)
- mono `#calibrationInfo` and `#poreSelectionInfo` (04, 05, 16)
- bright-blue Object details histogram (17): it now reads `--chart-bar`
- red text on the disabled "Delete selected" button (09)

## Requirements check

| Requirement | Result | Evidence |
|---|---|---|
| No Korean text in the UI | **Pass for `ui/`. Fail in the export path.** | No Hangul anywhere in `ui/*.js`, `ui/*.html` or `ui/*.css`. Hangul remains in `scripts/pore_details_export.py:72`, `report_docx.py` and `report_hwpx.py` (see P1-3 and P1-4). |
| No dark mode | **Pass** | `theme.css` sets only `color-scheme:light`. No `prefers-color-scheme` or `data-theme` exists in `ui/`. `report-ui.css` is gone. |
| Both modes look the same in the chrome | **Pass, with one leak** | `labimage.css` only shows or hides. Screenshots 08 (Report) and 09 (Labeling) share the header, rail, document bar, strip, well, inspector and status bar. The leak is the Labeling-only "Detection settings" panel in Report (P1-2). |

## Scores

### Audit health (technical), out of 20

| # | Dimension | Score | Key finding |
|---|---|---|---|
| 1 | Accessibility | 3 | Labels, names, focus ring and two-tone canvas ring are good. The status bar sticks on a busy message. Errors in the detached window are not marked as errors. |
| 2 | Performance | 3 | Lean, with no framework. `object-details.js` calls `getComputedStyle` once per bar or point inside the draw loop. |
| 3 | Theming | 3 | A full token system. A few canvas hex values remain, and the overlay colors collide (P2-4). |
| 4 | Responsive | 3 | 700, 900, 1100, 1280 and 1600 all hold without page scroll. The strip text and file name truncate at 1280. |
| 5 | Implementation integrity | 3 | A coherent, product-specific system. The export language does not match the preview. Three dead duplicate JS files remain. |
| | **Total** | **15/20** | **Good.** Fix the weak spots, not the system. |

**Integrity verdict: pass.** The yellow T#/D# readout chips match the overlay on the image. With the gray well and the indigo-only accent, this is clearly an SEM instrument, not a generic kit. The detector did not run, so this verdict rests on the source read and the screenshots.

### Design health (Nielsen), out of 40

| # | Heuristic | Score | Key issue |
|---|---|---|---|
| 1 | Visibility of system status | 2 | Status stuck on "Updating object details…". A stale "Analysis complete" shows on setup. |
| 2 | Match with the real world | 3 | T#/D#, µm and "Ridge trace/Width spot/SAM mask" are domain-true. |
| 3 | User control and freedom | 3 | Undo, Esc and Cancel exist everywhere. |
| 4 | Consistency and standards | 3 | The Columns dialog breaks the footer order and the icon rules. Two Undo buttons do the same thing. |
| 5 | Error prevention | 3 | The Report setup shows Detection settings that have no effect there. |
| 6 | Recognition over recall | 3 | At 1000–1279 the rail is icon-only. Point +/− rely on tooltips. |
| 7 | Flexibility and efficiency | 3 | S/T/A/D keys, key caps and Ctrl+Z work well. |
| 8 | Aesthetic and minimalist design | 3 | Quiet and exact. A small image sits top-left in a large empty well. |
| 9 | Error recovery | 2 | "already measured" does not say which tube, and the user must find it. |
| 10 | Help and documentation | 3 | Inline hints and "Measurement definitions" are present. |
| | **Total** | **28/40** | **Good** |

Cognitive load: 1 of 8 checklist items fails. On the Tube screen, the Tubes hint, the strip and the status bar repeat the same key instructions three times. Load is low.

## Findings

### P0 (blocking)

None.

### P1 (major: fix before release)

**P1-1. The status bar stays on "Updating object details…" after the dialog opens.** (This is the known issue; here is the root cause.)

> **Status: fixed.** `work()` in `ui/editor.html` now resets to "Ready." when the caller left its busy text. Verified live: status reads "Ready." after Object details opens.
- Location: `ui/editor.html:49`, `work(message,fn)`. It is called from `ui/object-details.js:197`.
- Problem: `work()` sets the busy message, but on success it only resets `busy`. Any caller that does not write its own final status leaves the busy text in place, with the Ready dot, indefinitely. Screenshots 16, 17 and 18 show this. Every `work()` caller is exposed, not only Object details.
- Fix: in `work()`, after `await fn()`, add `if($('status').textContent===message)setStatus('Ready.')`. Optionally also end the `openPoreDetails` callback with `setStatus('Object details updated.')`.
- Principle: visibility of system status. The status bar is "the single feedback channel" (spec 4.8).

**P1-2. "Detection settings" shows in Report mode and does nothing there.** (Known issue; root cause found.)

> **Status: fixed.** `#advancedSettings` carries `lab-label-only`; the JS toggle and the `.lab-inactive-detection` rule are gone. Verified live: hidden in Report setup, shown in Labeling setup.
- Location: `ui/labimage.js:110`, inside the `showProject` wrapper. Markup: `<details id="advancedSettings">` in `ui/editor.html:21`.
- Problem: the hiding class `lab-inactive-detection` is toggled only when `showProject` runs. Opening an analysis by another path leaves the panel visible (screenshot 04). Users can change Minimum area and Sampling, and nothing happens.
- Fix: add `lab-label-only` to the element, as in `<details id="advancedSettings" class="panel lab-label-only">`. The existing rule `body[data-lab-mode="report"] .lab-label-only{display:none!important}` then hides it by mode, not by code path. Delete the toggle at `labimage.js:110`.
- Principle: error prevention. Mode rules belong in CSS (spec 1.2, "Mode rules only show or hide elements").

**P1-3. The report plot fallback text is Korean and renders as empty boxes.**

> **Status: fixed.** Fallback is "No objects away from the image boundary." in `#454c55`. The unused Korean label set and `korean=` branch in `pore_details_export.py` were removed (no caller passed it).
- Location: `scripts/pore_details_export.py:72`, `draw_report_histogram`: `ax.text(... '경계에 닿지 않는 pore가 없습니다.' ...)`.
- Problem: "Exclude boundary objects" is checked by default in Add plot (screenshot 15). When every object touches the boundary, the English report figure shows this Korean string. In this path `report=True, korean=False`, so Malgun Gothic is never set and the glyphs render as empty boxes, both in the dialog preview and in the saved report.
- Fix: replace it with `'No objects away from the image boundary.'` and set `color='#454c55'` to match `--chart-axis`.
- Principle: English-only requirement, and the error says what happened.

**P1-4. Word and HWPX exports are in Korean, but the preview and the PDF are English.**

> **Status: fixed.** `report_docx.py` and `report_hwpx.py` use `1. Instrument and conditions`, `2. Method`, `3. Results`, `Not specified`, `Table N.`, `Figure N.`; Word run language `en-US`, HWPX package language `en`, preview HTML `lang="en"`. Malgun Gothic is kept (same as the PDF). The HWPX template's built-in Hancom style names and Korean font face names were left as is: they are Hancom identifiers, not report text. Verified: generated .docx and .hwpx are valid zips with parseable XML, English headings, no Hangul in the body.
- Location: `scripts/report_docx.py:171-195` and `scripts/report_hwpx.py:75-133`. Strings include `가) 분석기기 및 조건`, `나) 분석 방법`, `다) 분석 결과`, `미입력`, `표 N.` and `그림 N.`.
- Problem: one button, "Save PDF, HWPX and Word", writes three documents in two languages. The on-screen preview (screenshot 11: "1. Instrument and conditions") does not represent two of the three files. Spec 5.10 put exported content out of scope, but the English-only requirement and the preview contract both fail here.
- Fix: reuse the English section titles from the PDF/preview composer. Use `1. Instrument and conditions`, `2. Method`, `3. Results`, `Not specified`, `Table N.` and `Figure N.`. If Korean deliverables are still wanted, make the language a single explicit report option, so that preview and export match.
- Principle: implementation integrity. The preview must match the output.

### P2 (minor: next pass)

**P2-1. The strip hint is cut off at 1280 in "Width only" and in Select.** (Known; the Select case is new.)

> **Status: fixed.** Strip copy shortened (`TUBE_KINDS.d.strip`, `TOOL_UI.select.text`); `#tsText` gets the full text as `title`. The Tubes panel keeps the long hint. Verified at 1280: fits.
- Location: `ui/labimage.js`, `TUBE_KINDS.d.hint` and `TOOL_UI.select.text`. `ui/workspace.css:145` sets `.ts-text{max-width:70%;text-overflow:ellipsis}`. Line 163 reserves 400 px for the selection actions.
- Problem: screenshot 08 reads "Ctrl-click adds or remove…". The Width-only hint also loses its end. The important part, the modifier rule, is the part that gets cut.
- Fix: shorten the strip copy. The Tubes panel already carries the long kind hint.
  - `d.hint`: `'Click a clean, straight part of a tube.'`
  - `select.text`: `'Click to select. Ctrl-click adds or removes.'`
  - Also set `title` on `#tsText` to the full text.
- Principle: strip text fits on one line (spec 3.2 and QA at 1280).

**P2-2. The file name is cut from the end, which hides the part that tells files apart.**

> **Status: fixed.** `#editorImageName` has `min-width:19ch`; range sliders shrink first (96 px to 56 px). Names over 24 characters are middle-truncated (first 10, "…", last 12) with the full name in `title`; the report composer now reads the name from `title`. Verified at 1280: "CNT_powder_1kx-9.tif" shows in full.
- Location: `ui/workspace.css:115`, `#editorImageName{flex:1 1 0;min-width:0;text-overflow:ellipsis}`.
- Problem: at 1280, "CNT_powder_1kx-9.tif" shows as "CNT_powder_…" (screenshots 06, 08 and 10). SEM series differ only in the suffix (-9, -10). Two open analyses look identical.
- Fix: give the name a floor with `min-width:16ch`, and let the sliders shrink first (`#zoom,#poreOpacity{flex:0 1 96px;min-width:56px}`). In JS, middle-truncate: show the first 8 characters, then "…", then the last 10, and keep the full name in `title`.
- Principle: recognition over recall.

**P2-3. "already measured" does not say which tube.**

> **Status: fixed.** `lab_editor.py` names the covering object as the list labels it (`T4`, `D5` or `#4`). The UI appends "It is now selected. Delete it to trace again.", selects that object (outline on the canvas, row highlighted) and scrolls the row into view. Test updated to `^T1 is already measured`. Verified live with D5.
- Location: `scripts/lab_editor.py:154` (`'This tube is already measured.'`) and the suffix added at `ui/labimage.js:660`.
- Problem: the message says "Select it in the list", but it does not name the tube, so the user hunts through T1…Tn (screenshot 10).
- Fix: have the backend return the overlapping id in the message, for example `'T4 is already measured.'`. Then the UI selects that row (`tr[data-id]`, `.selected`, scroll into view) and highlights it on the canvas, so that "Select it" is already done.
- Principle: error recovery. Point at the source of the problem.

**P2-4. Overlay colors crowd the yellow–magenta band.**

> **Status: fixed.** Default object color is green `#27c66f` in both modes (a stored old default `#ffd700` is ignored), so yellow belongs to measurements only. Selection is a 2-screen-px outline, not a fill, and its color also avoids the measurement yellow, trace cyan and Replaced pink (now red-orange `#ff5533` by default). "Selected" is in the legend with a live dot. Replaced keeps `#ff5ab4`.
- Location: `ui/editor.html:29` (legend: Objects `#ffd700`, Preview `#ffa623`, Replaced `#ff5ab4`), `--measure:#ffff00`, and selection `#ff00ff` (`object-list.js:8` `contrastColor`).
- Problem: in Report, gold object outlines sit next to pure-yellow measurement paths, so the bold element is diluted. Selection magenta and "Replaced objects" pink are hard to tell apart, and selection is not in the legend. Screenshot 06 shows the selected D5 as a solid magenta blob that hides the feature it measures.
- Fix:
  - In Report, default `#poreColor` to a non-yellow color, such as `#00cde0` or white at 40 %. Then yellow belongs only to the measurements.
  - Draw the selected object as a 2 px outline, not a fill.
  - Add "Selected" to the legend, or move Replaced to a color far from magenta, such as `#4488ff`.
- Principle: one bold element (spec 1.1). Do not rely on near-identical hues.

**P2-5. A smaller image sits top-left in the well.**

> **Status: fixed.** `.viewport{display:grid}` + `.viewport>canvas{margin:auto}`. Zoom anchor, cursor overlay and click mapping all use `getBoundingClientRect`, so offsets are handled; scroll math only applies when the canvas is larger (margins are then 0). Verified live in both modes.
- Location: `ui/workspace.css:174`, `.viewport{overflow:auto}`. The canvas is not centered.
- Problem: in screenshots 08, 09 and 19, 40–60 % of each pane is empty gray to the right and below. The figure looks unaligned and the two panes look unbalanced.
- Fix: `.viewport>canvas{display:block;margin:auto}`, with `.viewport{display:grid}` so the auto margins center the canvas when it is smaller and scroll normally when it is larger. Then recheck the zoom anchor math in `comparison.js:55-57` and the cursor overlay, both of which assume offset 0.
- Principle: composition. The data is centered in the instrument.

**P2-6. The Columns dialog breaks the dialog system.**

> **Status: fixed.** Footer is Defaults … Cancel, Apply. Transfer buttons are "Show" + chevron-right and chevron-left + "Hide" (new `chevron-right` in `icons.js`). "Clear" is "Hide all". Verified live.
- Location: `ui/object-columns.js:49-52`.
- Problems:
  - The footer is `OK` then `Cancel`. Every other dialog uses Cancel then primary (spec 4.9).
  - The transfer buttons are the glyphs `>>` and `<<`. The spec bans glyph icons.
  - "Clear" is ambiguous: clear what?
- Fix:
  - Reorder the buttons to Cancel then OK, and rename OK to "Apply" to match the report dialogs.
  - Use chevron SVGs from `icons.js` with the visible labels "Show" and "Hide".
  - Rename "Clear" to "Hide all".
- Principle: consistency and standards.

**P2-7. In the detached Object details window, errors overwrite the selection line and look neutral.**

> **Status: fixed (code only).** `details-window.js` adds its own `<p id="detailsStatus" role="status">` after the selection row; `setStatus(text,error)` toggles `.error` (`--danger`) and every catch passes `true`. Not verified live: the detached window needs the pywebview API.
- Location: `ui/details-window.js:7` and line 13. `setStatus(message)` writes into `#poreSelectionInfo` with no error state. `work()` catches with `setStatus(error.message)`.
- Problem: export failures read like the normal "No selection" text. Nothing is announced, and the selection count is lost.
- Fix: give the window its own `<p id="detailsStatus" role="status">` in the footer. Add `setStatus(text,error)` that toggles `.error` (`--danger`), and pass `true` in the catch.
- Principle: visibility of system status, and errors announced (spec 1.4, UX Error Messages).

### P3 (polish)

**P3-1. The setup panel keeps a stale "Analysis complete: 2 objects in 6s." and a full 6 px progress bar.**

> **Status: fixed.** `showPanel('setup')` clears the job message and resets the bar unless busy.
- Location: `ui/workspace.js:222`.
- Problem: when the user returns to setup (screenshots 04 and 05), the old message and bar read as a second button underline.
- Fix: clear `jobMessage` and hide `#analysisProgress` when the panel is shown, unless a job is running.

**P3-2. Dead duplicate files.**

> **Status: skipped.** Still referenced: `customize.py` edits `ui/pore-columns.js`, and the `source/` copy (`source/ui/editor.html`, `source/ui/details-window.html`, `source/scripts/pore_editor.py`) loads all three. `packaging/` does not list them.
- Location: `ui/pore-details.js`, `ui/pore-columns.js` and `ui/pore-list.js` are loaded nowhere. They duplicate `object-*.js`, including the old glyphs.
- Fix: delete them, and check that `packaging/` does not list them.
- Principle: integrity. Avoid two sources for one UI.

**P3-3. Instructions are repeated on the Tube screen.**

> **Status: skipped.** Not a one-liner (collapsing keys under "Keys" and removing the panel Undo, which also drives the rail Undo's disabled state).
- Problem: the strip steps, the Tubes kind hint and `#tubeHint` (with all the key caps) say the same thing. The rail Undo and the Tubes "Undo" call the same `labUndo()`.
- Fix: keep the key list only in `#tubeHint`, collapsed under "Keys". Drop the panel's Undo button, or label it "Undo tube edit" if the panel should keep a local control.

## Not verified

- Reduced motion was not emulated. In code, `theme.css:277` is a global 0 ms kill. The busy bar and the fresh row have intentional static alternatives (`workspace.css:588-590`). Dialog fade becomes 0 ms. This looks correct in code, but nobody has watched it run.
- The PDF preview, Add contents and image preview dialogs were never opened. Their markup is correct: icon close buttons with names, `aria-labelledby`, and token styling. Their sizing (`#reportPdfDialog` at 90vh, iframe flex) is unverified.
- Screenshot 15 (Add plot) shows the dialog semi-transparent over the page. This is most likely a capture taken mid `dlgIn` fade (240 ms). Recapture it after 300 ms to confirm.
- Contrast was not measured by pixel. Token ratios in the spec were trusted.
- Keyboard tab order was not tested.
