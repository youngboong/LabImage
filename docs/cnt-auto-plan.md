# CNT auto-detect plan (Fable)

## Goal

One button finds the tubes whose two ends are both clearly visible inside the image, and proposes each as a
candidate centerline. Tubes that cross or pass under another tube count as one tube. The user accepts or rejects
candidates; an accepted candidate becomes a normal tube object (T + D), exactly like a click-traced one.

User's words: "watershed나 그런거 이용해서 중간에 겹쳐서 막히는것도 이어져있는걸로 해서 처음과 끝이 확실하게
되있는 거는 자동분석", "자동 감지가 잘 작동했으면 좋겠음". Also reported: click traces wiggle onto other
tubes at crossings.

## What exists (reuse, do not rewrite)

- `scripts/cnt_detect.py`: `centerline_map` (learned P, 0.09 s/image), `ridge_response`, `track_segment`
  (position x heading cheapest path, `TRACK_TURN`, P blend), `trace_tube(gray, ridge, points)`,
  `finish_candidate` (clean-section D), `tube_mask`.
- `scripts/lab_editor.py`: `tube_ridge` (cache), `trace_tube`, `tube_annotation`, routes `/api/trace-tube`,
  `/api/measure-tube`.
- `scripts/cnt_eval.py`: GT from (2) yellow lines, `eligible`, `mag_bin`, `sym_dist`, `--model oof`, folds.
- `validation/cnt-learn/oof/`: out-of-fold P maps for all 42 images. `validation/cnt-learn/folds.json`.
- UI Tube tool and Tubes panel in `ui/labimage.js`.

## Steps

1. **Straight through crossings (tracker).** At a crossing every strand looks like a centerline. Make the path
   prefer to keep its heading through the crossing (for example penalise change of turn, or raise the turn cost
   only where P is high in several directions). Raising `TRACK_TURN` globally was tested and rejected:
   1.0 and 2.0 help <300x but make >=1kx worse (`validation/cnt-learn/grid-turn/`).
2. **Candidate graph.** P -> hysteresis threshold -> skeleton -> graph of end points and junctions. Prune spurs.
   At each junction pair the branches that continue straightest with similar width. Bridge a gap when two free
   ends face each other, are close, and are aligned (tube hidden under another). A chain from free end to free
   end is one candidate.
3. **Certainty filter.** Keep a candidate only if: both ends are away from the image border and the info bar;
   the tube really ends at both ends (no centerline response beyond the end); every junction pairing on the
   chain was unambiguous; length above a minimum. Give each candidate a score.
4. **Refine.** Feed the chain's ends and a few interior points to the existing `trace_tube` as waypoints, then
   `finish_candidate` for D. The saved geometry is the tracker's, so auto and manual tubes look the same.
5. **App.** `/api/detect-tubes` returns candidates (path, length, score). Tubes panel gets "Find tubes".
   Candidates are drawn in a distinct preview style; click one to accept, plus "Accept all" and "Clear".
   Accept reuses the existing save path. Candidates overlapping an existing object are dropped. English UI,
   light theme, existing tokens.
6. **Evaluation.** `cnt_eval.py --auto` on out-of-fold P: per magnification bin, recall of the simple GT tubes
   (a candidate matches when symmetric distance and length error are inside a tolerance), number of proposals
   per image, and how many proposals match no label. The labels are not exhaustive, so unmatched proposals
   must also be judged by eye on overlay images.

## Known limits

- Dense tangles will give few or no candidates. That is acceptable: wrong proposals cost more than missing ones.
- Earlier auto detection was dropped for quality. The new input is the learned map, which did not exist then.
- Only 42 labelled images; no new training is planned. Train an end-point map only if steps 1-4 fall short.

## Process

Design and verification: Opus. Coding: Sonnet (high). UI coding: Opus, with frontend-design, ui-ux-pro-max,
impeccable. Do not replace `_internal/` or `LabImage.exe` while LabImage is running.

## Design (verified)

Verified 2026-11-10 with prototypes in `validation/cnt-auto/proto/`:

- `graph.py`: the candidate graph.
- `run_graph.py`: features and matching.
- `table.py`, `diag_tips.py`, `diag_oracle.py`, `refine.py`, `tracker_cross.py`.
- `overlays/`: overlay images.

All numbers come from the 42 eligible images and the out-of-fold maps in `validation/cnt-learn/oof/`. GT comes from `cnt_eval.gt_tubes`:
70 certain simple tubes (`<300x` 30, `300-800x` 17, `>=1kx` 23). The shipped checkpoint was never run on these images.

### Verdict

**Do not build steps 2-5 as planned.** On this data the candidate graph finds 5 of 70 labelled tubes raw. After the certainty filter it
finds 3 of 70 (4 %).

Any method that joins free ends on the P skeleton has a low ceiling here:

- Only 18 of 70 labelled tubes (26 %) have both GT tips at a free tip of the P skeleton.
- For those 18, an oracle handed the correct pair of tips gets a matching path for only 6 (skeleton geodesic) or 7 (`trace_tube`).

So better pairing rules can raise recall to about 10 % at most. The user's tubes are bundles that touch, fray into or end inside other
material. In P they are not isolated strands with two free ends.

**Leave the tracker (step 1) alone.** I tried nine crossing-aware turn-cost variants. Each one helps some tubes a lot and hurts others a lot.
None is "not worse in any bin".

**Match tolerance.** Every match uses `cnt_eval.matches(candidate, gt, W)`:

- At least 70 % of each path must lie within `max(6, .75*W)` px of the other path.
- `W` is the chain width: 2 x the median distance transform of the P mask along the skeleton.
- The trace evaluation already uses this rule, so auto and click numbers are comparable.
- The rule also bounds length error to about 30 %.

The tolerance does not limit recall. Only 5 of 70 GT tubes have any free-free chain that covers even 50 % of them in both directions
(`cover` in `run_graph.py`).

### M1. Candidate graph (measured)

Algorithm as prototyped (`graph.build`):

1. `mask = apply_hysteresis_threshold(P, low, high)`, then `skeletonize`.
2. Junction pixels are skeleton pixels with >= 3 neighbours. Cluster them 8-connected.
3. The rest of the skeleton becomes ordered segments. Each segment has width `W = 2*median(edt(mask))` along it.
4. Contract junction clusters joined by a segment `<= merge*W` into one node. A crossing skeletonises as two 3-way junctions.
5. Prune spurs: tip-to-junction segments shorter than `max(spur*W, 8)` at nodes of degree >= 3. Up to 3 rounds.
6. Pair branches at each node:
   - Branch direction runs from 0.5W to 2W out of the node.
   - A pair is valid if its deviation from straight is `<= dev`. At degree-2 nodes the limit is `<= 60` deg.
   - At degree >= 3 nodes, the width ratio must also be `<= 1.6`.
   - Pick pairs greedily by deviation.
   - A pair is ambiguous if another valid pair sharing a branch is within 15 deg.
7. Optional gap bridge between two free tips that face each other. Conditions:
   - distance `<= gap*W`;
   - both headings within 30 deg of the joining line;
   - width ratio `<= 1.6`;
   - each tip is the other's nearest valid partner.
8. Walk chains end to end. Record how many ends are free tips (`free` = 0, 1 or 2).

A candidate is a chain with `free == 2` and `L >= 60` px. `L` is measured after extending each tip along its heading while `P >= 0.5`, by
at most 1.5W.

**Sweep.** 32 configs:

- hysteresis (.3,.6), (.4,.7) or (.5,.8);
- `dev` 30 or 45;
- `merge` 1 or 2;
- `spur` 1, 2 or 3;
- holes filled: 0 or 400 px;
- gap 0 or 3.

Best: `low .5, high .8, dev 45, merge 1, spur 2, holes 0, gap 3`. The gap bridge never changed recall (0 to 2 proposals per bin).

| bin | certain GT | found | recall | proposals/img | on certain GT | on other yellow label | on no label |
|---|---|---|---|---|---|---|---|
| <300x | 30 | 1 | 0.03 | 5.8 | 1 | 0 | 57 (98 %) |
| 300-800x | 17 | 1 | 0.06 | 5.7 | 1 | 0 | 67 (99 %) |
| >=1kx | 23 | 3 | 0.13 | 7.7 | 3 | 2 | 148 (97 %) |
| all | 70 | 5 | 0.07 | 6.6 | 5 | 2 | 272 (97 %) |

**Diagnostics at (.5,.8), all 42 images:**

| chains counted | recall | proposals/img |
|---|---|---|
| at least one free end | 0.11 | 31 |
| ends anywhere | 0.36 | 101 |

- Both GT tips at a free skeleton tip (within `max(W, 15)` px): 0.30 / 0.18 / 0.26 by bin, 0.26 overall.
- Both GT tips on the skeleton at all: 0.99.

### M2. Certainty filter (measured)

Each rule is added on top of the rules above it, applied to the M1 candidates:

| rule | recall (all) | proposals/img | on no label |
|---|---|---|---|
| none | 5/70 | 6.6 | 97 % |
| both extended tips `>= max(W, 10)` px from the border (gray is already cut at the info bar) | 4/70 | 4.4 | 97 % |
| + "really ends": strongest mean P on 5 rays (+-20 deg), 0.5W to 2W beyond each tip, `< 0.3` | 3/70 | 1.8 | 96 % |
| + no ambiguous pairing on the chain | 3/70 | 1.8 | 96 % |
| + `L >= max(60, 5W)` | **3/70** | **1.3** | 95 % |
| + 5th-percentile P along the chain `>= 0.5` | 3/70 | 1.3 | 95 % |

Final rule by bin:

| bin | found | proposals/img |
|---|---|---|
| <300x | 0/30 | 1.0 |
| 300-800x | 1/17 | 0.8 |
| >=1kx | 2/23 | 1.8 |

The filter drops 2 of the 5 raw matches: `1kx-16` (5 px from the border) and `200x-29` (`beyond` 0.36). A score was not worth defining at
this recall.

**What the unmatched proposals are.** I checked by eye on 8 overlays (GT magenta, kept cyan, rejected orange):
`validation/cnt-auto/proto/overlays/CNT_powder_{1kx-12,2kx-10,500x-1,200x-3,1kx-15,500x-21,100x-12,1kx-5}_filtered.png`. The raw chains are
in `*_raw.png`.

Kept (8 in these images):

- 2 match GT: `1kx-15`, `500x-21`.
- 3 are real unlabelled tubes or bundles, isolated, with both ends visible: `1kx-15` #3, `1kx-5` #2, `2kx-10` #1.
- 1 is a wrong pairing that joins two tubes through a knot: `1kx-5` #4.
- 1 is info-bar text: `2kx-10` #5. `detect_information_footer` returns 818 on this image, but the Tescan bar starts at about 768. This is
  an existing bug, and it also affects `cnt_eval`.
- 1 is a short fibril fragment in debris: `200x-3` #0.

Rejected:

- tubes that leave the image;
- fringe fibrils around tangles (all proposals of `500x-1`; its 4 GT tubes lie inside the tangle and form no chain);
- squiggles on debris;
- footer text.

Missed:

- `1kx-12`: the certain GT is a U-shaped bundle inside a tangle. The long clean tube in this image is labelled, but it is not a certain
  simple tube because of its loop, and its left end sits in the loop crossing.
- `100x-12` and `200x-3`: the GT tubes are straight bundle segments in a packed field.

### M3. Refinement (measured, n = 5 matched raw chains)

`trace_tube(gray, ridge, [tip0, k interior chain points, tip1])` with `ridge['P'] = oof P`. Each cell gives sym distance (px) and signed
length error.

| image | raw chain | k=0 | k=1 | k=2 | k=3 |
|---|---|---|---|---|---|
| 1kx-15 | 3.1, +0.097 | 3.7, +0.029 | 4.9, +0.003 | 3.5, +0.053 | 4.3, +0.011 |
| 1kx-16 | 1.2, +0.106 | 1.7, +0.046 | 2.3, +0.054 | 2.4, +0.055 | 2.6, +0.052 |
| 1kx-6 | 3.1, +0.094 | 3.2, +0.018 | 3.1, +0.017 | 3.7, +0.019 | 3.6, +0.022 |
| 200x-29 | 9.1, +0.008 | 9.4, -0.084 | 10.7, -0.094 | 11.4, -0.105 | 11.1, -0.107 |
| 500x-21 | 1.0, +0.057 | 1.3, +0.008 | 1.2, +0.002 | 1.1, +0.003 | 1.1, +0.012 |

- `k = 0` is enough. The tracker removes the raw chain's ~+10 % length bias. That bias comes from the P blob reaching past the tube end.
- Interior points do not help.
- Chain waypoints can coincide, and then `trace_tube` raises `Choose distinct trace points.` A builder must drop points closer than 1 px.

### M4. Tracker crossing fix (measured, rejected)

The smallest change tried raises the bend cost only at crossings. In `track_segment`, before the P blend:

```python
top, k0 = response.max(0), response.argmax(0)
second = max of response over orientations >= CROSS_SEP*22.5 deg from k0
cross = clip(second/top, 0, 1)*clip(top, 0, 1); cross[cross < CROSS_MIN] = 0
turn edge weight = abs(turn)*TRACK_TURN*width*(1 + CROSS_GAIN*cross[Y, X])
```

It was monkeypatched by `tracker_cross.py` (OOF, 42 images, about 10 s per config). The baseline run reproduces
`validation/cnt-learn/report.md` (L0.6) exactly. Values are sym median / p90 in px:

| bin | wp | current (L0.6) | gain 4, min 0 | gain 4, min .6 | gain 4, min .7 | gain 4, min 0, sep 3 |
|---|---|---|---|---|---|---|
| <300x | 0 | 7.63 / 17.1 | 6.65 / 19.6 | 7.44 / 16.5 | 7.59 / 20.1 | 7.21 / 19.9 |
| <300x | 1 | 3.60 / 11.4 | 3.37 / 7.8 | 3.52 / 11.0 | 3.52 / 11.2 | 3.50 / 9.0 |
| <300x | 2 | 3.05 / 5.4 | 2.57 / 4.8 | 3.05 / 5.4 | 3.05 / 5.7 | 2.54 / 5.2 |
| 300-800x | 0 | 17.11 / 53.2 | 17.03 / 49.8 | 16.73 / 53.4 | 17.11 / 53.2 | 19.19 / 49.8 |
| 300-800x | 1 | 11.61 / 32.1 | 11.49 / 25.7 | 11.72 / 30.4 | 11.45 / 27.8 | 11.82 / 23.6 |
| 300-800x | 2 | 10.53 / 18.1 | 8.87 / 14.8 | 10.53 / 17.3 | 10.53 / 18.1 | 9.31 / 16.7 |
| >=1kx | 0 | 9.47 / 25.3 | 7.47 / 40.0 | 6.91 / 25.4 | 6.90 / 25.1 | 6.95 / 25.1 |
| >=1kx | 1 | 6.83 / 15.1 | 6.72 / 20.8 | 6.83 / 19.4 | 6.68 / 11.5 | 6.62 / 10.6 |
| >=1kx | 2 | 5.33 / 7.4 | 6.24 / 10.3 | 5.23 / 9.1 | 5.37 / 9.1 | 5.80 / 10.0 |

Also tried, all worse in at least one cell:

- gain 2 at min 0 and at min .5;
- gain 8 at min .7 (same result as gain 4);
- gain 4 and gain 8 at min .5 with sep 3.

Per tube, the pattern is clear. At 0 waypoints every variant helps: `>=1kx` goes from 9.47 to about 6.9, `1kx-13` from 16 to 7, `200x-4` from
30 to 15, `700x-25` from 27 to 15. But a higher bend cost at a crossing also stops the path from following a real bend that happens to lie on
a crossing:

- `1kx-4` wp1: 7.8 to 56.5;
- `200x-5` wp0: 13 to 29;
- `500x-1` wp1: 8 to 25;
- `2000x-8` wp2: 7 to 14.

In every variant the `>=1kx` 2-waypoint p90 gets worse (7.4 to 9.1-10.3).

Not tried: a second-order "change of turn" penalty. It needs a (cell, heading, last turn) lattice with 3x the nodes, so it is not a small
change.

### M5. Runtime (measured, 42 images, one process, Core Ultra 9 285K)

| stage | median | max |
|---|---|---|
| `centerline_map` (OpenVINO, measured earlier) | 0.09 s | 0.18 s first call |
| `ridge_response` (cached per image by `tube_ridge`) | 0.76 s | 1.3 s |
| graph + features + filter | 0.28 s | 0.41 s |
| refine kept chains with `trace_tube`, k = 0 | 0.10 s | 0.60 s |

The whole detect call takes at most about 2.4 s. Runtime is not the problem.

### What it would take, and gates (only if the user still wants it)

Two options remain open. Neither has been measured.

- **(a) "Find isolated tubes".** Ship M1 + M2 + M3 as they are, and say plainly that the button proposes only isolated tubes.
  - About 1.3 proposals per image.
  - 5 of the 8 kept proposals reviewed by eye were real tubes (2 labelled, 3 unlabelled).
  - Recall of the tubes the user actually measures: 4 %.
- **(b) Semi-automatic.** The user clicks one end and the app proposes the other end. Not prototyped.

The plan's fallback, an end-point map, does not fix the main loss: the oracle test above already has perfect ends and still traces only 7 of
18 tubes.

If (a) is built, `graph.py` and `refine.py` in the proto folder are the reference implementation. Constants for `cnt_detect.py`:

```
AUTO_P_LOW, AUTO_P_HIGH = .5, .8
AUTO_MERGE = 1.0, AUTO_SPUR = 2.0, AUTO_SPUR_MIN = 8
AUTO_DEV = 45, AUTO_DEV2 = 60, AUTO_WIDTH_RATIO = 1.6, AUTO_AMBIGUOUS = 15
AUTO_END_P = .5, AUTO_BEYOND = .3, AUTO_MIN_LENGTH = 60, AUTO_MIN_LENGTH_W = 5
```

- `detect_tubes(gray, ridge) -> list[dict]`: `trace_tube` dicts plus `score`, built from `ridge['P']`. Returns `[]` when there is no P.
- `cnt_eval.py --auto` (with `--model oof`): writes `auto.md` and `<stem>_auto.png`. `auto.md` holds the per-bin table in the M1 format and
  the M3 refinement medians for matched candidates.

Tests (synthetic, in the style of `tests/test_cnt_detect.py`):

- An isolated S-curve gives 1 candidate with sym <= 3 px.
- An X crossing gives 2 candidates, each running straight through.
- A tube touching the border gives 0 candidates.
- The stem of a T-junction gives 0 candidates.
- No P gives `[]`.

Gates to ship (`cnt_eval --auto --model oof`):

| gate | target | measured now |
|---|---|---|
| recall, all bins | >= 0.30 | 0.04 |
| recall, each bin | >= 0.20 | 0 / 0.06 / 0.09 |
| proposals per image | <= 3 | 1.3 |
| kept proposals that are real tubes (by eye, 8 overlays) | >= 80 % | 5/8 |
| refined sym median, matched | <= 4 px | 3.2 (n=3 kept) |
| refined length median abs error, matched | <= 0.05 | 0.018 (n=3) |
| detect time per image | <= 3 s | 2.4 s max |

### Honest list of what fails

- **Recall.** The labelled tubes are mostly bundles whose ends touch, fray into or sit inside other material. 74 % of them do not have two
  free tips in P.
- **Pairing.** Even with the right two tips, 11 of 18 tubes take a wrong route. This happens at low magnification, where P merges
  neighbouring bundles, and at knots.
- **Footer.** `detect_information_footer` misses 50 px of the Tescan bar on `2kx-10`.
- **Tracker.** The crossing errors are real (`1kx-13`, `200x-4`, `700x-25` at 0-1 waypoints). Turn-cost tweaks trade them for new errors at
  real bends.
- **Not verified:**
  - unmatched proposals on the other 34 images (only 8 of 42 were checked by eye);
  - M3 beyond the 5 tubes it was measured on;
  - runtime on any machine except this one;
  - the deployed model, which was not used, by design.
