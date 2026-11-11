# CNT "Detect tubes" retry under the measurement criteria (design + verification)

Status: prototype measured on 42 images with out-of-fold (OOF) centerline maps. **Recommendation: do not ship as a
default button.** If the user still wants it, ship it as an explicitly labelled "Find isolated tubes (experimental)" at the
operating point below. The implementation notes at the end are ready for that case.

Prototype: `validation/cnt-auto2/` (`detect.py`, `run.py`, `table.py`, `overlay.py`; overlays in `overlays/`). The earlier study
is in `docs/cnt-auto-plan.md`, sections M1-M5.

## What changed from the first attempt

The user's criteria remove the hard cases: no overlapped or touching objects, no standing objects, no objects cut by the
border or the info bar, and ends must be the real outline ends. So this detector does **not** pair branches through junctions
(M1 in the plan). It accepts a strong P component only when that component is already a single, free, whole tube.

## Method (`detect.py`)

All lengths are in px, or in multiples of `W` (the P blob width: `2*median(edt(mask))` on its skeleton).

1. `mask = apply_hysteresis_threshold(P, 0.5, 0.8)`. Label it 8-connected. Skip components with bbox < 20 px.
2. Per component (in a crop padded by 40 px):
   - Fill holes no larger than `4*W^2`. A larger hole means a loop or a crossing: reject as `loop`.
   - Skeletonize. Main path = geodesic diameter of the skeleton (two MCP passes).
   - Side branches: the farthest skeleton pixel from the main path must be `<= max(2W, 8)`. Otherwise reject as `branched`.
   - Extend each tip along its heading while `P >= 0.5`, by at most 1.5W (the same as `extend` in the first study).
3. Features and rejection order (first failing rule wins):
   - `short`: `L < max(60, 5W)`.
   - `cut`: an extended tip lies within `max(W, 10)` px of the image border. `gray` is already cut at `detect_information_footer`,
     so this rule also covers the info bar.
   - `touching`: the loose blob (`P >= 0.25`) that holds the chain also holds another strong component with area
     `> 2W^2`, reaches farther than `2.5W` from the chain, or runs out of the padded crop.
   - `crowded`: more than `1*W^2` px of another loose blob lies within `W/2 + max(W, 6)` of the chain.
   - `no_end`: the strongest mean P on 5 rays (+-20 deg), 0.5W to 2W beyond either tip, is `>= 0.3`. The tube visibly continues.
   - `weak`: the 10th percentile of P along the traced path is `< 0.9`. **This rule removes most of the background-texture false
     positives** (see below).
4. Survivors are traced by the shipped code: `trace_tube(gray, ridge, [tip_a, tip_b])`, with 0 waypoints, which the first study
   found to be best (M3). The saved line, L and D therefore come from the same code path as a two-click trace.

The foreground-isolation test that was suggested (gray band versus flanks) was tried as a feature. It did **not** separate good
from bad: background streaks at 2.5 kx have a contrast of 0.8-1.3 image std, and the real tube `1kx-19` #52 has 0.56. P
strength (`p10P`) separated them; contrast did not, so contrast is not used.

## Results (42 images, 70 certain GT tubes, OOF P)

Recommended operating point (`low .5, high .8, loose .25, spur 2W, hole 4W^2, attached 2.5W, touch_area 2W^2, near 1W^2,
beyond .3, p10 .9, min length max(60 px, 5W), border max(W, 10) px`):

| bin | images | certain GT | found | recall | proposals | per image | on certain GT | on other yellow label | unlabelled |
|---|---|---|---|---|---|---|---|---|---|
| <300x | 10 | 30 | 0 | 0.00 | 1 | 0.1 | 0 | 0 | 1 |
| 300-800x | 12 | 17 | 1 | 0.06 | 3 | 0.2 | 1 | 0 | 2 |
| >=1kx | 20 | 23 | 2 | 0.09 | 7 | 0.3 | 2 | 2 | 3 |
| all | 42 | 70 | 3 | 0.04 | 11 | 0.26 | 3 | 2 | 6 |

The same point without the `p10` rule gives 39 proposals (0.9 per image), 3 on certain GT, 3 on other labels, and 33 unlabelled,
most of them background texture.

Matched proposals (trace vs GT):

| tube | sym distance px | length error |
|---|---|---|
| 1kx-15 #12 (the "7"-shaped tube) | 4.9 | -0.045 |
| 1kx-16 #16 | 1.7 | +0.028 |
| 500x-21 #9 | 1.4 | +0.003 |

**All 11 proposals were checked by eye** (overlays: GT certain yellow, proposals cyan, rejected skeletons coloured by reason):

| proposal | verdict |
|---|---|
| 1kx-15 #12, 1kx-16 #16, 500x-21 #9 | match certain GT, good trace |
| 1kx-16 #3 (thick bundle), 2000x-8 #15 (curled fibre) | on another yellow label; real isolated objects |
| 1kx-15 #18 | real isolated frayed bundle, both ends visible, unlabelled |
| 1kx-26 #11 | real isolated short tube, unlabelled |
| 200x-6 #15 | real tube (it is a certain GT tube), but the trace bends inside the wide frayed crescent and cuts the top end: wrong line |
| 700x-25 #48 | curved fibre beside a debris flake: ambiguous |
| 1kx-9 #15 | faint short fibril fragment in the background: wrong |
| 500x-21 #7 | curl on a debris piece: wrong |

Precision: **7 of 11 are correct as proposed** (64 %). 8 of 11 are real objects. 1 is ambiguous and 2 are wrong. This is below
the 80 % gate set in the first plan.

Before the `p10` rule I also checked 2.5kx-18, 1kx-19, 700x-25, 200x-4 and 1kx-16. Their extra proposals (#7, #10, #26 and #38 in
2.5kx-18; #37 and #39 in 1kx-19; #11 in 700x-25; #4 and #31 in 200x-4; #8 and #22 in 1kx-16) are all background texture or
faint fibril pieces whose real ends are not visible.

### Why recall is low: most labelled tubes are not "isolated" in P

This is the component that covers at least half of each certain GT tube, at the recommended point:

| reason | GT tubes |
|---|---|
| inside a P network with holes (`loop`) | 54 |
| branches > 2W off the main path (`branched`) | 10 |
| component accepted by the geometry rules (3 of these were also matched) | 4 |
| no strong component | 2 |

So 64 of 70 labelled tubes sit in a connected network in P. I checked this by eye on 12 overlays:
500x-22 (2), 200x-29 (3), 200x-6 (4 of 5), 2000x-8 (2), 200x-4 (3), 700x-25 (1), 1kx-26 (1) and the left tube of 1kx-15. All of
these GT tubes lie inside, cross, or end in clutter or bundles. Under the new criteria they are correctly not proposed.

In those 12 images only about 5-6 GT tubes are clearly isolated and whole. The detector finds 3 of them. It misses:

- **1kx-9**: the long isolated tube. One faint fibril touches it near its left end, so the component is `branched` (side 3.6W).
- **1kx-15**, bottom right (unlabelled): a side fibril at its left end gives `branched`.
- **200x-6** crescent: proposed, but traced wrongly.

Structural sweeps did not change the result. Hysteresis (.6, .85) and (.7, .9), and spur 3W, all give 11-15 proposals with the
same 3 GT matches.

### Runtime (14 parallel worker processes, Core Ultra 9 285K)

| stage | median | max |
|---|---|---|
| `ridge_response` (already cached per image by `tube_ridge`) | 1.0 s | 1.6 s |
| `candidates` (all components, all features) | 0.38 s | 0.73 s |
| `trace_tube` of survivors only (first run) | ~0 s | 0.38 s |

`centerline_map` adds about 0.1 s (measured earlier). One click costs under 1 s after the ridge is cached.

## Failure cases

- **Fibril contact**: one faint fibril touching a clean tube makes it `branched` or `touching`, and the tube is lost. This is the
  main loss on the images where isolated tubes exist (1kx-9, 1kx-15).
- **Background texture at >= 2 kx**: P fires on bright streaks. The `p10 >= .9` rule removes most of them, but not all.
- **Wide frayed bundles at low magnification**: `trace_tube` with 0 waypoints can cut a corner (200x-6 #15).
- **Small debris curls** pass every geometric rule (500x-21 #7).
- **Footer**: `detect_information_footer` misses 50 px of the Tescan bar on `2kx-10` (known bug, plan M2). With `p10` that
  proposal is gone, but the bug remains.
- **Standing objects**: there is no rule for them. They appear short or blob-like and mostly fail `short`. Not verified.

## Recommendation

**No-ship as a regular feature.** It gives 0.26 proposals per image. About 1 in 3 is wrong or needs a redo, and it finds 3 of the
70 labelled tubes (about half of the clearly isolated ones). On these 42 images the user would save one two-click trace every 4-5
images, and would also delete a wrong proposal every ~10 images. That does not pay for a button and a new endpoint.

If the user wants it anyway (for example, on future images that are more dispersed, like 1kx-15 and 1kx-16), ship it as
**"Find isolated tubes (experimental)"** at the operating point above. Say plainly that it skips anything touching. Raising
`p10` to .95 was not measured.

The one change likely to raise recall is to cut thin side fibrils at junctions (side branch blob width < 0.5 x main width)
instead of rejecting the component. That brings back the pairing logic, which was what lost precision in the first study. It
was not tried.

## Implementation notes (only if shipped)

### `scripts/cnt_detect.py`

```python
AUTO_P = (.5, .8); AUTO_LOOSE = .25; AUTO_SPUR = 2.; AUTO_SPUR_MIN = 8; AUTO_HOLE = 4.
AUTO_MIN_LENGTH = 60; AUTO_MIN_LENGTH_W = 5; AUTO_BORDER = 10; AUTO_GAP = 1.; AUTO_GAP_MIN = 6
AUTO_BEYOND = .3; AUTO_ATTACHED = 2.5; AUTO_TOUCH_AREA = 2.; AUTO_NEAR = 1.; AUTO_P10 = .9

def detect_tubes(gray, ridge):
    """Isolated, whole tubes with two free ends; [] without a centerline model. Each item is a trace_tube dict plus 'score'."""
```

- Port `candidates`, `main_path`, `extend`, `beyond` and `reason` from `validation/cnt-auto2/detect.py`. The `prune` and
  `order` functions there are dead code: drop them.
- If `ridge.get('P') is None`, return `[]`.
- For each survivor: `c = trace_tube(gray, ridge, [path[0], path[-1]])`. Catch `ValueError` and skip. Compute `p10P` on
  `resample(c['path'])` and drop the candidate when it is `< AUTO_P10`. Set `c['score'] = p10P`. Sort by score, descending.
- Tips are `extend`ed points. Clip them to the image before calling `trace_tube` (it rejects points outside).

Tests, synthetic, in the style of `tests/test_cnt_detect.py`. Build P by hand and `ridge = dict(R=..., sigma=..., P=P, ...)`:

- One isolated S-curve gives 1 candidate with sym <= 3 px.
- An X crossing gives 0.
- A T-junction gives 0.
- A tube within 5 px of the border gives 0.
- Two parallel tubes 0.5W apart give 0 (`crowded`).
- `P=None` gives `[]`.

### `scripts/lab_editor.py`: `POST /api/detect-tubes {dataset, revision, kind}`

- Add the path to the POST allow-list (line ~415) and dispatch it under `editor.lock` after `check_revision`, like
  `/api/trace-tube`.
- `kind` must be `'td'` or `'t'` (as for traces).
- `detect_tubes(self, state, payload)`:
  1. `ridge = self.tube_ridge(state)`, then `cands = detect_tubes(state['gray'], ridge)`.
  2. Build `occupied` from `state['masks']` once. For each candidate:
     - `full = tube_mask(shape, c['path'], c['band_px'])`;
     - if `(full & occupied).sum() > 0.2*full.sum()` or `(full & ~occupied).sum() < 20`, count it as `skipped['overlaps_existing']`;
     - otherwise `occupied |= full` and keep it.
  3. Save **once**, using the same mask and annotation construction as `add_tube`:
     `masks[id] = full & ~occupied_before`, `annotations[str(id)] = tube_annotation(c, kind)`, ids `next_id..`. Then call
     `self.save(state, masks, annotations, history+[revision], next_id, dict(type='detect-tubes', object_ids=ids, kind=kind))`.
     Factor the shared part of `add_tube` into a helper rather than calling `add_tube` in a loop: each call to `add_tube`
     saves its own revision, which would break the "one undo" requirement.
  4. Return `dict(result, object_ids=ids, skipped=dict(overlaps_existing=n, trace_failed=m), tubes=[self.tube_values(state, c, kind) ...])`
     (`trace_failed` = candidates whose `trace_tube` raised, counted inside `detect_tubes`). When `ids` is empty, do not save a
     revision: return `object_ids=[]` and the counts, so the UI can say "No isolated tubes found".
- Without the model (`P is None`), return 400 with "Detect tubes needs the centerline model."

## Risks and unverified points

- Precision (7/11) and recall rest on **11 proposals**: too few for a stable number. The confidence interval is wide.
- All numbers use OOF P. The shipped model was trained on all images, so it is likely to look better on these images and is not
  measured here.
- `p10 >= .9` was chosen on the same 42 images that are reported. No held-out check was possible.
- No rule detects standing objects.
- Unmatched rejected components were not reviewed for missed isolated tubes, except on the 12 overlays I opened.
- Runtime was measured in a 14-process pool, not in the app process.
- The UI (button, review of proposals, delete) is not designed here.

## Blur / thin-fibril suppression test (2026-11-11)

**Question.** Does washing out fine detail before detection let clean tubes that touch a faint fibril pass? **Answer: no.** No
variant beats the baseline (11 proposals, 3 matches, 7 correct). The best alternative, Gaussian sigma 3 px, finds one more
labelled tube (1kx-14) but adds more wrong proposals: 6 of 14 are correct.

**Setup.**
- Same 42 images, same 70 certain tubes, same thresholds as the recommended operating point.
- **P is recomputed on the degraded image with each image's own fold model**
  (`validation/cnt-learn/fold{k}.xml` via `folds.json`), so every number stays out-of-fold. Sanity check: sigma 0.01 reproduces
  the stored-OOF baseline exactly.
- The degraded P is used only for detection, including the `p10` rule. Survivors are re-traced with `trace_tube` on the
  **original** gray, with the original OOF P.
- Prototype: `PRE` and `CFG` environment variables in `validation/cnt-auto2/run.py`. Results are in `v_*.pkl`.
- `scripts/lab_footer.py` changed today (it now cuts the Tescan bar at 768 on 1kx-13, 1kx-16, 1kx-24 and 2kx-10). The stored
  OOF maps are cropped to match, in `validation/cnt-auto/proto/common.py`. The re-run baseline is unchanged: 11 / 3.

"Wrong" means checked by eye on the overlays. A partial trace of a real tube counts as wrong. Rows marked "n/i" were not
inspected, because they already lose matches and proposals.

| variant | proposals | match certain GT (of 70) | other label | unlabelled | correct / wrong / ambiguous (by eye) | matched sym px | matched length error |
|---|---|---|---|---|---|---|---|
| baseline (stored OOF P) | 11 | 3 | 2 | 6 | 7 / 3 / 1 | 4.9, 1.8, 1.4 | -.045, +.028, +.003 |
| **Gaussian blur on gray** | | | | | | | |
| sigma 2 px | 10 | 3 | 1 | 6 | 5 / 4 / 0, plus 1 real tube with a poor line | 4.6, 1.2, 18.1 | -.056, -.005, -.083 |
| sigma 3 px | 14 | 3 | 5 | 6 | 6 / 7 / 1 | 1.6, 4.2, 1.6 | -.005, -.048, -.017 |
| sigma 5 px | 18 | 2 | 2 | 14 | n/i | 4.4, 6.1 | -.068, +.117 |
| sigma 0.3 x tube width (from sato scale) | 11 | 1 | 4 | 6 | n/i | 17.9 | -.10 |
| **Thin-structure opening of the P blob** (disk radius = f x W, largest piece kept, same opening on the loose blob) | | | | | | | |
| f = 0.2 | 11 | 3 | 2 | 6 | same 11 proposals as baseline: 7 / 3 / 1 | 4.0, 1.8, 1.4 | -.049, +.028, +.002 |
| f = 0.3 | 11 | 2 | 3 | 6 | n/i | 4.6, 1.3 | -.069, +.004 |
| f = 0.4 | 8 | 2 | 2 | 4 | n/i | 4.2, 1.3 | -.062, +.006 |
| **PoreSAM `prepare_adjustable`** | | | | | | | |
| normalize only | 11 | 2 | 2 | 7 | n/i | 5.1, 1.2 | -.026, +.010 |
| background_strength 3 | 8 | 1 | 2 | 5 | n/i | 1.9 | -.016 |
| background_strength 8 | 3 | 0 | 1 | 2 | n/i | | |
| background_strength 15 | 0 | 0 | 0 | 0 | n/i | | |
| background 3 + kuwahara 3 | 7 | 2 | 0 | 5 | n/i | 2.4, 6.9 | -.029, +.076 |
| background 3 + gaussian 4 | 11 | 2 | 1 | 8 | n/i | 4.9, 7.6 | -.16, +.078 |
| kuwahara 4 only | 11 | 2 | 1 | 8 | n/i | 1.8, 4.5 | -.023, -.098 |

**What I saw.**

- **Gaussian sigma 3.**
  - New: 1kx-14 hook-shaped tube (correct, sym 1.6 px) and the 1kx-16 lower frayed bundle (real).
  - Lost: 1kx-16 #16 and 2.5kx-18 S-tube. Both are proposed, but only part of each tube is traced, because blur merges the
    tube with a neighbouring fibril and moves the tip.
  - New wrong proposals: 1kx-13 tube fragment in a tangle, 1kx-19 background streak, 700x-25 fibril in debris, and 120x-7 curl
    on debris. The 500x-21 debris curl remains.
  - Blur widens P, so a fibril and a tube merge **more**, not less. 15 GT tubes lose their component entirely: `no_component`
    rises from 2 to 15.
  - The target misses are **not** recovered: the 1kx-9 long tube and the 1kx-15 bottom-right tube are still rejected.
- **Gaussian sigma 2.** It drops 1kx-16 #16 and 1kx-26 #11, both correct. It adds three faint background fibrils (1kx-5 #7, and
  1kx-6 #5 and #15).
- **P-blob opening.**
  - f = 0.2 changes nothing.
  - Larger f erodes real thin tubes (the 1kx-16 GT is lost) before it cuts the side fibrils. The fibrils that block 1kx-9 and
    1kx-15 survive f = 0.2. In P they are apparently not much thinner than the tubes. Their widths were not measured.
- **PoreSAM.**
  - It hurts. `background_strength` is a grey-scale **opening** with that radius. On bright-on-dark SEM it erases bright
    structures narrower than about 2r, so the tubes go too: 3, then 0 proposals at strength 8 and 15.
  - Normalisation alone already loses one match. Its 2/98 % stretch clips the input differently from the 1/99 stretch the
    model was trained on.
  - Kuwahara and Gaussian blur on top of it behave like the plain blur, only worse.

**Conclusion.** Degrading the input does not help. Blur merges neighbours, which is the opposite of what the isolation test
needs. Opening P cannot tell a thin side fibril from a thin tube. The PoreSAM filters remove the tubes themselves. The
recommendation stands: no-ship. If the button is shipped anyway, keep the unblurred operating point.

Overlays for the best alternative (Gaussian sigma 3): `validation/cnt-auto2/overlays-blur/<stem>.png`. Three sigma-2 overlays
are in `validation/cnt-auto2/overlays-g2/`.
