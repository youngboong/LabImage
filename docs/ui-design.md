# LabImage UI design spec (v2, light, one system)

Date: 2026-11-09. Status: spec for implementation. No project file was changed when this was written.

Scope: `ui/editor.html`, `ui/details-window.html`, `ui/labimage.js`, `ui/labimage.css`, `ui/workspace.css`, `ui/report-ui.css`, `ui/workspace.js`, `ui/region-queue.js`, `ui/comparison.js`, `ui/object-*.js`, `ui/report-composer.js`.
Both workspaces, Labeling and Report, use this spec. They differ only in which tools and panels exist.

How to read it: section 1 sets the direction, section 2 is the full token file, section 3 is the shell, section 4 has the components, section 5 maps every screen to its ids and copy, and section 6 is the migration and QA plan.

Line numbers drift because another agent is editing `ui/labimage.js`. This spec names code by **string or id**, not by line. Grep for the quoted string before you edit.

---

## 1. Direction

### 1.1 Statement

**Bench instrument.** LabImage should read like the control surface of a measuring instrument on a lab bench: a light, cool, machined-gray body with graphite labels and one dark indigo "ink" accent. The image well is the only dark-ish area. All color in the image belongs to the data: pure yellow `#ffff00` for measurements, cyan for the live trace. The chrome stays quiet and exact, so a reader's eye goes to the yellow numbers on the gray SEM image and then to the same numbers in the readout table.

The one memorable element is the **readout**. Tube IDs appear as pure-yellow `T3` / `D3` key chips with black monospace text, exactly as they look on the figure. Values use tabular monospace digits. A user can match the table to the image in a glance. Everything else is disciplined: system sans, small radii, hairline structure, no decoration.

Mode: **Operate** (impeccable). Ambition shows as precision, consistency and complete states, not as expression.

### 1.2 Requirements this direction meets

| Requirement | How |
|---|---|
| English only | All Korean strings and `lang="ko"` spans are removed (section 5.9). The `.ko` style is deleted. |
| Light theme only | `color-scheme: light` on `:root`. There is no `prefers-color-scheme` block. The dark `report-ui.css` is deleted. |
| One design system | `ui/theme.css` holds the tokens, element base and components. Layout rules lose their `body[data-lab-mode="report"]` scope and apply to both modes. Mode rules only show or hide elements. |
| System fonts, offline | Segoe UI Variable / Segoe UI / system-ui. Cascadia Mono / Consolas for numerals. No webfonts, no framework, no build step. |
| Tabular numerals | `font-variant-numeric: tabular-nums` on `body`. Readout cells use `--font-mono`. |
| WCAG AA, visible focus, reduced motion | Contrast ratios are listed per token (section 2). There is one focus ring token, with a two-tone variant on the image well. Durations become 0 ms under `prefers-reduced-motion`. |

### 1.3 Image well: neutral mid-gray, justified

The well (`.viewport`, `.setup-canvas-wrap`, image-card thumbnails) is **`#4c4c4c`, hue-free, about L\* 32**. A light well was considered and rejected for three reasons:

1. **Simultaneous contrast.** SEM micrographs are mostly dark to mid gray. A white surround (L\* ~100) makes the whole image look darker and flattens shadow detail, and users judge tube edges from that detail. ISO 3664/12646 practice for judging images calls for a neutral gray surround for this reason.
2. **Letterbox glare.** At 1280 px a 4:3 image leaves 30–40 % of the well empty. A white letterbox would be the brightest area on screen and would compete with the yellow `#ffff00` labels. On `#4c4c4c`, yellow measures 8.0:1 and cyan `#37e6ff` measures about 5.6:1, so both stay the strongest marks.
3. **Overlay legibility.** The live trace draws a white rubber band and white point discs. White on `#4c4c4c` is 8.6:1. On a light well they would disappear at the image edge.

The well is gray, not near-black. It sits at 7.2:1 against the app background, so the frame is clear without a heavy black slab inside a light app.

### 1.4 Skill findings: adopted and rejected

**frontend-design** (loaded). Followed: ground the design in the subject (SEM measurement vocabulary: T#/D#, yellow overlay, scale), spend boldness in one place (the readout), and write copy in plain sentence case with verbs that name the action. Checked against its list of generated-design tells and changed accordingly:
- Rejected the "SaaS card kit": the inspector is **one continuous column with hairline section dividers**, not a stack of rounded shadowed cards (the current Report inspector is a stack of cards).
- Removed "template chrome": the home eyebrow `LOCAL IMAGE WORKSPACE · SAM 2.1`, the `01 / LABELING` card indexes, `→`/`↗` appended to buttons, and middle-dot meta strings (`A · B · C`). Section 5.10 rewrites these.
- Monospace is used only for numbers, IDs and units (data), never for labels.
- Numbered markers are used only where the content is a sequence: the 4-step stepper and the 3 Tube steps.

**ui-ux-pro-max** (searches run: `--design-system "scientific instrument measurement desktop tool precision" --density 9 --motion 2 --variance 3`, `--domain color`, `--domain typography`, `--domain style`, 8 `--domain ux` queries, `--stack html-tailwind`).

| Finding | Decision | Why |
|---|---|---|
| Style: Minimalism & Swiss Style (grid, functional, high contrast, visible focus, reduced motion) | **Adopted** | Fits an Operate instrument. Its accessibility requirements are the brief's. |
| Pattern: Minimal Single Column, "large centered CTA" | **Rejected** | A landing-page pattern. LabImage is a three-column tool. |
| Palette: "Operation orange on dark" (`#EA580C` on `#1C1917`) | **Rejected** | Dark mode is banned, and orange sits next to the yellow overlay on the hue wheel and competes with it. |
| Palette: "Research Lab / University Department" (`#F8FAFC` bg, navy `#1E3A5F` primary, `#CBD5E1` border, `#475569` muted text) | **Adopted in structure, changed in values** | The light institutional structure fits. The navy primary moved to indigo ink `#3a3f9e`, which is further from the cyan trace and still reads as one accent. Its amber accent `#A16207` was dropped (it competes with the yellow). Its serif headings were dropped (system sans only). |
| Typography: "Dashboard Data" (Fira Code for data, Fira Sans for labels) | **Concept adopted, fonts rejected** | Mono for data and sans for labels became Cascadia Mono + Segoe UI Variable, because the app is offline and uses system fonts only. Inter (design-system result) was rejected for the same reason. |
| Style: Data-Dense Dashboard (`gap 8px`, `padding 12px`, `12–14px` text, `row 36px`, sticky headers) | **Adopted with changes** | Rows are 32 px, gaps 8 px, sticky table heads and feet. KPI cards and chart widgets were rejected; the readout table is the KPI. |
| UX: Focus States (High), Reduced Motion (High), Excessive Motion | **Adopted** | One focus token. Durations go to 0 under reduced motion. Only state changes animate. |
| UX: Target Size (Minimum), WCAG 2.2 AA, 24×24 CSS px | **Adopted** | Mouse-driven desktop app. Controls are 28 px tall, small icon buttons 24 px. The mobile 44 pt / 48 dp rule does not apply. |
| UX: Loading Indicators (avoid a flash for near-instant work) | **Adopted** | The busy bar appears after a 300 ms delay. |
| UX: Error Messages (aria-live / role=alert) | **Adopted** | `#status` keeps `role=status`. Inline field errors use `role=alert` only when the user caused them. |
| UX: Toasts auto-dismiss after 3–5 s | **Adopted for success only** | Errors stay in the status bar until the next action. |
| UX: Table Handling (horizontal scroll) | **Adopted** | Tables scroll inside their wrapper. The page never scrolls sideways. |
| Motion preset: GSAP scroll reveal | **Rejected** | No dependency, and no scroll reveals in a tool. |
| Stack | **No match** | The database has no plain HTML/CSS/vanilla JS stack. The nearest stack, `html-tailwind`, returned Tailwind-only advice (prose plugin, `@utility`), so it was rejected. Only its general reduced-motion guidance applies. |
| Effects: hover transitions 200–250 ms | **Changed to 90–160 ms** | Users work in a tight click loop. impeccable Operate guidance is 150–250 ms for most transitions; hover uses the faster end. |

**impeccable** (loaded: SKILL.md, craft-floor.md, operate.md, audit.md). *The launcher failed (the engine download needs network), so `impeccable context` and `detect` did not run; the project has no PRODUCT.md or DESIGN.md.* The spec pre-empts these audit findings:

| impeccable rule | Current violation | Spec fix |
|---|---|---|
| Eyebrow above a heading is a ban | Home `.lab-eyebrow` | Removed. |
| No colored `border-left`/`border-right` above 1 px | `#toolStrip{border-left:3px}`, `#tools button.active{box-shadow:inset 3px 0}`, `.results tr.selected{inset 3px 0}` | Active and selected states use a fill plus a 1 px accent outline. |
| No glyphs or emoji as icons | `＋` upload, `↗` Object Details, `↻` refresh, `☰` drag handle, `×` close, `→` | Inline SVG from one 24-unit, 1.75-stroke set (section 4.12). |
| Gradient as decoration | `#tubePanel` linear-gradient | Removed. |
| Mono as costume | none yet | Mono only in numeric cells, IDs, units, zoom/opacity values. |
| Browser surfaces themed | Scrollbars themed only in Report; no `::selection`, no caret color | Section 2 base: `::selection`, `caret-color`, scrollbars, `accent-color`, tabular numerals. |
| Every component has default, hover, focus, active, disabled, loading, error | Partial | Section 4 lists all states per component. |
| Inconsistent vocabulary across screens | Labeling uses text-button toolbars; Report uses an icon rail. Two themes. | One rail, one theme, one button set. |
| Modal as first thought | Object details is a dialog, but it is also a separate window | Kept: it is a data inspector that the user opens on purpose. No new modals. |
| Contrast ≥ 4.5:1 | Labeling Home button 1.07:1 (white on white) | Removed with the old theme; every text token is ≥ 4.84:1 on its surfaces. |

### 1.5 Review of the plan against generic defaults

Checked against the frontend-design calibration list before writing tokens:
- Not cream with a terracotta accent: the base is cool gray (`#e9ebee`).
- Not near-black with an acid accent: dark mode is banned. The image well is gray, not black.
- Not a broadsheet: radii are small but not zero (3/5/8/12 by hierarchy). Hairlines separate inspector sections only.
- Not the SaaS card kit: one radius per level, shadows only on floating layers (popover, dialog, toast), and no washes.
- Changed during review: the first draft had a 2 px indigo underline under the active step and a left accent bar on the active tool. Both copied the current dark theme's habits and broke the border-left rule, so they were replaced by a filled step number and a filled tool tile.

---

## 2. Tokens: `ui/theme.css` (new file, shared by both modes)

Load it **first** in `ui/editor.html` and `ui/details-window.html`. Contrast ratios were computed with the WCAG 2.x formula. Surfaces: app `#e9ebee`, panel `#f6f7f8`, raised `#ffffff`, sunken `#dfe2e6`.

```css
/* ui/theme.css: LabImage design tokens, element base and shared components.
   Light theme only, by requirement; there is deliberately no dark variant.
   Image colors (--measure, --trace) are data colors: never use them for chrome text or fills. */
:root{
  color-scheme:light;

  /* ---- surfaces ---- */
  --surface-app:#e9ebee;      /* window background, home screen */
  --surface-panel:#f6f7f8;    /* header, inspector, toolbars, status bar */
  --surface-raised:#ffffff;   /* inputs, tables, dialogs, setup panels, cards */
  --surface-sunken:#dfe2e6;   /* tool rail, table head/foot, segmented track */
  --surface-hover:#e6e9ed;    /* hover fill on panel and raised surfaces */
  --surface-pressed:#d6dade;  /* :active fill */
  --well:#4c4c4c;             /* image well, hue-free; see section 1.3 */

  /* ---- lines ---- */
  --line:#c9ced5;             /* decorative dividers only (1.48:1 on panel; not used for control edges) */
  --line-strong:#7d858f;      /* control boundaries: 3.48 panel, 3.73 raised, 3.13 app (WCAG 1.4.11 >= 3:1) */

  /* ---- text ---- */
  --text:#1a1d21;             /* 15.77 panel, 16.91 raised, 14.16 app, 13.01 sunken */
  --text-2:#454c55;           /* secondary: 8.10 panel, 8.68 raised, 7.27 app, 6.68 sunken */
  --text-3:#58616b;           /* tertiary, hints, units: 5.87 panel, 6.29 raised, 5.27 app, 4.84 sunken, 5.08 accent-soft */
  --text-disabled:#8b939d;    /* 2.90 panel; disabled controls are exempt from 1.4.3 */
  --text-on-accent:#ffffff;   /* 8.81 on --accent, 11.40 on --accent-hover */
  --text-on-well:#e9ebee;     /* pane captions drawn over the well: 7.19 */

  /* ---- accent: indigo ink. Primary action, selection, current step, focus. Nothing else. ---- */
  --accent:#3a3f9e;           /* text use: 8.21 panel, 8.81 raised, 7.37 app, 7.11 accent-soft */
  --accent-hover:#2c3080;
  --accent-soft:#e4e6f6;      /* selected fill */
  --focus:#3a3f9e;            /* focus ring; 8.21 vs panel */
  --focus-on-well:#ffffff;    /* inner ring on the image well: 8.59 vs --well */

  /* ---- status ---- */
  --ok:#1d6b45;     --ok-soft:#e3f1e9;      /* 6.04 panel, 5.56 on soft */
  --warn:#8a5300;   --warn-soft:#fbefd9;    /* 5.90 panel, 5.56 on soft */
  --danger:#b3261e; --danger-soft:#fbe5e3;  /* 6.09 panel, 5.42 on soft, white on it 6.54 */
  --danger-hover:#8f1d17;                   /* white on it 8.91 */

  /* ---- image/data colors (canvas and readout chips only) ---- */
  --measure:#ffff00;          /* measurement overlay yellow; black on it 19.56; 8.0 on --well */
  --measure-ink:#000000;
  --measure-edge:rgba(0,0,0,.45); /* chip border, so yellow keeps an edge on white (yellow/white is 1.07) */
  --trace:#37e6ff;            /* live tube trace; read by labimage.js traceColor(); ~5.6 on --well */
  --trace-ink:#04121a;
  --chart-bar:#3a3f9e;        /* read by histogram() in editor.html */
  --chart-axis:#454c55;

  /* ---- type ---- */
  --font-ui:"Segoe UI Variable Text","Segoe UI",system-ui,"Malgun Gothic",sans-serif; /* Malgun only as a fallback for user file names */
  --font-display:"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;
  --font-mono:"Cascadia Mono","Cascadia Code",Consolas,ui-monospace,monospace;
  --fs-11:11px;  /* key caps, table sub-labels, rail labels */
  --fs-12:12px;  /* hints, field labels, table head */
  --fs-13:13px;  /* body, controls, table cells (base) */
  --fs-14:14px;  /* panel and section titles */
  --fs-16:16px;  /* dialog titles, stepper at >=1600 */
  --fs-20:20px;  /* screen titles (Load image, Image and scale) */
  --fs-32:32px;  /* home title only */
  --lh-tight:1.25; --lh:1.45;
  --fw-regular:400; --fw-semibold:600;

  /* ---- spacing (4 px base) ---- */
  --sp-1:2px; --sp-2:4px; --sp-3:6px; --sp-4:8px; --sp-5:12px;
  --sp-6:16px; --sp-7:20px; --sp-8:24px; --sp-9:32px; --sp-10:48px;

  /* ---- sizes ---- */
  --ctl-h:28px;      /* default control height */
  --ctl-h-sm:24px;   /* small and icon buttons: WCAG 2.5.8 minimum */
  --ctl-h-lg:32px;   /* primary actions on setup and report screens */
  --row-h:32px;      /* table rows */
  --header-h:48px;
  --toolbar-h:40px;  /* document bar and tool strip */
  --status-h:28px;
  --rail-w:64px;
  --inspector-w:352px;

  /* ---- radii: one per level ---- */
  --r-1:3px;   /* key caps, chips */
  --r-2:5px;   /* controls, rail tiles, image well */
  --r-3:8px;   /* setup and report panels, image cards */
  --r-4:12px;  /* dialogs, home mode cards */
  --r-pill:999px;

  /* ---- borders ---- */
  --bw:1px;
  --border:var(--bw) solid var(--line);
  --border-ctl:var(--bw) solid var(--line-strong);

  /* ---- shadows: floating layers only ---- */
  --shadow-1:0 1px 2px rgba(26,29,33,.10);                                  /* segmented thumb, pressed-out tiles */
  --shadow-pop:0 2px 4px rgba(26,29,33,.08),0 8px 24px rgba(26,29,33,.14);  /* popovers, menus, toasts */
  --shadow-dialog:0 4px 8px rgba(26,29,33,.08),0 24px 56px rgba(26,29,33,.22);
  --backdrop:rgba(26,29,33,.32);

  /* ---- z-layers (dialogs use the top layer) ---- */
  --z-base:0; --z-sticky:10; --z-rail:20; --z-popover:100; --z-toast:200; --z-home:300;

  /* ---- motion ---- */
  --dur-1:90ms;    /* hover, press */
  --dur-2:160ms;   /* expand, collapse, segmented thumb */
  --dur-3:240ms;   /* dialog and toast enter */
  --ease-out:cubic-bezier(.16,1,.3,1);
  --ease-std:cubic-bezier(.2,0,0,1);
  --busy-delay:300ms;
}
@media (prefers-reduced-motion:reduce){
  :root{--dur-1:0ms;--dur-2:0ms;--dur-3:0ms}
}
```

### 2.1 Element base (also in `theme.css`, after the tokens)

```css
*,*::before,*::after{box-sizing:border-box}
html{background:var(--surface-app)}
body{margin:0;font:var(--fw-regular) var(--fs-13)/var(--lh) var(--font-ui);color:var(--text);
  background:var(--surface-app);font-variant-numeric:tabular-nums;accent-color:var(--accent);
  -webkit-font-smoothing:auto}
h1,h2,h3{margin:0;font-weight:var(--fw-semibold);line-height:var(--lh-tight);color:var(--text);text-wrap:balance}
button,input,select,textarea{font:inherit;color:inherit}
a{color:var(--accent);text-underline-offset:2px}
::selection{background:var(--accent-soft);color:var(--text)}
input,textarea{caret-color:var(--accent)}
:focus{outline:none}
:focus-visible{outline:2px solid var(--focus);outline-offset:2px}
.hidden{display:none!important}   /* JS contract: workspace.js, labimage.js, tests */
[hidden]{display:none!important}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.hint{font-size:var(--fs-12);line-height:var(--lh);color:var(--text-3);margin:var(--sp-4) 0}
.hint.error,.error{color:var(--danger)}
.mono,.num{font-family:var(--font-mono);font-variant-numeric:tabular-nums slashed-zero}
*{scrollbar-width:thin;scrollbar-color:var(--line-strong) transparent}
::-webkit-scrollbar{width:10px;height:10px}
::-webkit-scrollbar-thumb{background:var(--line);border:3px solid transparent;border-radius:var(--r-pill);background-clip:content-box}
::-webkit-scrollbar-thumb:hover{background:var(--line-strong);background-clip:content-box}
body.is-busy{cursor:progress}
```

---

## 3. Shell layout

Both modes use the same shell. Mode only changes which tools and panels exist.

```
≥1280 px
┌ header 48 ─────────────────────────────────────────────────────────────────────────────┐
│ LabImage │ Report   (1) Load image  (2) Set scale  (3) Segment and measure  (4) Report   SAM 2.1 on CPU  [Workspaces] │
├──────┬──────────────────────────────────────────────────────────────┬──────────────────┤
│ rail │ document bar 40: name · Fit · Zoom ─o─ 58% · Objects ■ · Opacity ─o─ 40% · IDs · Save images │ inspector 352 │
│  64  ├──────────────────────────────────────────────────────────────┤  one column,     │
│      │ tool strip 40: [icon] Tube  (1) Click one end — (2) … — (3) … [Length + Width|Length only|Width only] │ hairline sections│
│      ├──────────────────────────────────────────────────────────────┤                  │
│      │ image well (--well), 1 or 2 panes, fills the rest            │                  │
│      ├──────────────────────────────────────────────────────────────┤                  │
│      │ legend 24 (pore tools only)                                  │                  │
├──────┴──────────────────────────────────────────────────────────────┴──────────────────┤
│ status bar 28: ● Ready                                                                  │
└─────────────────────────────────────────────────────────────────────────────────────────┘
```

The middle row is drawn with ` · ` only to save space in this diagram; the UI itself has no middle dots.

### 3.1 Header and stepper (one 48 px row)

- **DOM change (one line, labimage.js):** move `nav.steps` into `header` right after `.app-brand`:
  `document.querySelector('header .app-brand').after(document.querySelector('nav.steps'));`
  This removes a 44 px row (chrome falls from 89 px to 48 px) and keeps the tab order brand, steps, engine, Home. Ids, `data-panel` and `aria-current` are unchanged.
- `header`: `height:var(--header-h); display:flex; align-items:center; gap:var(--sp-6); padding:0 var(--sp-6); background:var(--surface-panel); border-bottom:var(--border)`.
- `.app-brand h1`: `--fs-14`, semibold, "LabImage". `#labModeBadge` follows it as plain text in `--text-2`, separated by a 1 px × 16 px `--line` rule (`border-left` on the badge, 1 px, which is allowed). The pill and dot are removed.
- `.app-brand span` (engine): move it visually to the right with `margin-left:auto` on a wrapper. Simpler: give `.app-brand` `display:contents` and set flex `order`: `h1` 0, `#labModeBadge` 1, `.steps` 2, engine span 9 (`margin-left:auto; font-size:var(--fs-12); color:var(--text-3)`), `#labHomeButton` 10. Visual order then matches the wireframe. Tab order is unaffected because only the steps and Home are focusable, and they stay in DOM order.
- `.steps` is a flex row with `gap:var(--sp-1)` and height 100 %. Step button: height 32 px, padding `0 var(--sp-4)`, ghost style, `--fs-13`. The number is `display:inline-grid; place-items:center; width:20px; height:20px; border-radius:var(--r-pill); background:var(--surface-sunken); color:var(--text-2); font:600 var(--fs-11) var(--font-ui); margin-right:var(--sp-3)`.
  The number is a bare text node in the current DOM (`1 <span>Load Image</span>`). Wrap it once in JS (`<b class="step-n">1</b>`) or leave the text and style the button. Recommendation: wrap it in `labSetMode` when the labels are set.
- States: active (`.active`, `aria-current="step"`) gets a filled number (`--accent` with white text) and a semibold `--text` label, with no underline. Enabled is `--text-2`, hover is `--surface-hover`, and disabled is `--text-disabled` with `cursor:not-allowed`.
- Labeling keeps `[data-panel="analysis"]` at `display:none` (the smoke test checks this).

### 3.2 Editor grid (`#editorPanel`, both modes)

Port the current Report grid without its mode scope and switch it to tokens:

```css
#editorPanel{display:grid;height:calc(100vh - var(--header-h));padding:0;gap:0;
  grid-template-columns:var(--rail-w) minmax(0,1fr) var(--inspector-w);
  grid-template-rows:auto auto minmax(0,1fr) auto auto var(--status-h);
  grid-template-areas:"rail doc side" "rail strip side" "rail view side" "rail legend side" "rail notice side" "status status status"}
#editorPanel>.left{display:contents}
.document-toolbar{grid-area:doc} #toolStrip{grid-area:strip} #selectionActions{grid-area:strip}
.comparison-viewports{grid-area:view} .legend{grid-area:legend} #legacyOverlap{grid-area:notice}
#status{grid-area:status} #editorPanel>aside{grid-area:side;min-height:0;overflow:auto}
#tools{grid-area:rail}
```

- **`#selectionActions` shares the strip cell** (`justify-self:end; align-self:center; padding-right:var(--sp-5)`). It shows only for `data-tool=select|delete`, and the strip's `.ts-keys` hide in those tools. The strip row height is fixed at `--toolbar-h`, so **the canvas never moves when the tool changes**. The smoke test requires this: "Image jumps between Select and Add/Delete".
- The rail, inspector and status bar sit flush against the window edges. Separation uses 1 px `--line` borders, not gaps, so the image well gets every pixel.
- Tube mode keeps the current single-pane rule: `body[data-tool=tube] .comparison-viewports{grid-template-columns:minmax(0,1fr)}` and `body[data-tool=tube] .comparison-pane:first-child{display:none}`. `comparison.js` `fit()` already ignores the hidden pane.
- `body[data-tool=tube] :is(.legend,#editorPanel>aside>.panel:has(.metric),.lab-controls,#regionPanel,#previewPanel){display:none}` stays as it is today.

### 3.3 Tool rail (`#tools`)

- Background `--surface-sunken` with `border-right:var(--border)`. Vertical flex, `gap:var(--sp-1)`, padding `var(--sp-4) var(--sp-2)`, `overflow-y:auto`.
- Tile: full width × 52 px, radius `--r-2`, transparent, `--text-2`. The icon is 20 px, `stroke:currentColor`, width 1.75. The label is `--fs-11`. The key cap sits absolutely at top-right 3 px.
- States: hover is `--surface-hover` with `--text`. Active (`.active` + `aria-pressed=true`) is `--surface-raised` fill, `1px solid var(--accent)` border, `--accent` icon and label, and `--shadow-1`. Disabled is `--text-disabled`. Focus uses the global ring with `outline-offset:-2px`.
- `.tool-sep`: 1 px `--line` with 6 px margins.
- The Tube icon no longer uses `--trace` (cyan on the light rail is 1.4:1 and fails 1.4.11; cyan belongs to the image only).

### 3.4 Image well

- `.comparison-viewports`: `display:grid; grid-template-columns:1fr 1fr; gap:var(--sp-2); padding:var(--sp-2); background:var(--surface-app)`.
- `.comparison-pane h2` (Original, Segmentation): a 24 px caption bar on `--surface-panel`, `--fs-12` semibold `--text-2`, radius `--r-2 --r-2 0 0`.
- `.viewport`: `background:var(--well); border-radius:0 0 var(--r-2) var(--r-2)`.
- Canvas focus is a two-tone ring, because a single indigo ring is 1.02:1 on the well: `canvas#image:focus-visible{outline:2px solid var(--focus-on-well);outline-offset:-2px;box-shadow:inset 0 0 0 4px var(--focus)}`.
- Cursor: `crosshair` for drawing tools (set by JS), `default` for Select.

### 3.5 Inspector (`#editorPanel>aside`)

- Background `--surface-panel`, `border-left:var(--border)`, `overflow-y:auto`, no gap.
- Every `.panel` inside: `background:none; border:0; border-radius:0; border-bottom:var(--border); padding:var(--sp-5) var(--sp-6)`. Section title `h2` is `--fs-14` semibold, with `margin-bottom:var(--sp-4)`.
- Order (CSS `order`, as today): `#tubePanel` 1, `.lab-controls` 2, `#regionPanel` 3, `#previewPanel` 4, `#poreListPanel` 5, `.panel:has(.metric)` 6, `#manualPanel` 7, `#labMeasurementSettings` 8. Labeling has no report-only panels, so it shows 2, 3, 4, 5.
- `#manualPanel`: drop the yellow `#fffef7` background and the `#d8b956` border (`labimage.css`). It becomes a normal section.

### 3.6 Status bar (`#status`)

- 28 px, full width, `--surface-panel`, `border-top:var(--border)`, `--fs-12`, padding `0 var(--sp-6)`. `::before` is an 8 px dot.
- Ready: `--ok` dot, `--text-2` text.
- Busy (`body.is-busy`): `--accent` dot. A 2 px indeterminate bar along the top edge (`::after`, `animation:labBusy 1.1s var(--busy-delay) linear infinite`) fades in only after 300 ms. With reduced motion the bar is static and 100 % wide at 40 % opacity, so the state still shows.
- Error (`.error`): `--danger-soft` background, `--danger` text and dot. The message stays until the next status.

### 3.7 Responsive behavior

| Width | Behavior |
|---|---|
| **≥ 1600** | `--inspector-w:384px`. Rail tiles 56 px tall. Stepper labels `--fs-13`. |
| **1280–1599** | Default tokens (rail 64, inspector 352). |
| **1000–1279** | `--inspector-w:304px; --rail-w:56px`. Rail labels hide (`.tl` gets `.sr-only` styling); icon, key cap, `aria-label` and tooltip stay. Document bar: the words "Zoom" and "Opacity" become sr-only, sliders are 56 px, and `#zoomLabel`/`#poreOpacityValue` stay. Tool strip: `.ts-keys span:nth-child(n+3)` hidden. Stepper: step labels shorten through `data-short` (`Load`, `Scale`/`Setup`, `Measure`/`Label`, `Report`), set by JS once, shown with `content:attr(data-short)`. |
| **< 1000** | The editor becomes one column: `grid-template-columns:minmax(0,1fr); height:auto`; areas `"rail" "doc" "strip" "view" "legend" "notice" "side" "status"`. The rail becomes a horizontal, sticky (`top:0; z-index:var(--z-rail)`), x-scrolling strip of 64 × 48 tiles. `.comparison-viewports{min-height:60vh}`. The document bar and the tool strip may wrap. The header's stepper scrolls sideways inside its own box (`overflow-x:auto`), so the page itself never does. `.setup-grid` becomes one column. Home cards become one column below 760 px. |

At 900 px (QA width) the `< 1000` row applies.

---

## 4. Components (all in `theme.css`)

The global state vocabulary applies to every interactive component: **default, hover, active (pressed), focus-visible, selected/checked, disabled, busy, error**. Hover uses `--dur-1`, and nothing else animates on hover.

### 4.1 Buttons

Base `button` is the **secondary** button. Classes add variants. Existing class names are kept: `primary`, `danger`, `wide`, `active`, `icon-button`, `icon-btn`, `sm`, `stop-operation`.

```css
button{display:inline-flex;align-items:center;justify-content:center;gap:var(--sp-3);
  min-height:var(--ctl-h);padding:0 var(--sp-5);border:var(--border-ctl);border-radius:var(--r-2);
  background:var(--surface-raised);color:var(--text);font-size:var(--fs-13);line-height:1;cursor:pointer;
  transition:background-color var(--dur-1) var(--ease-std),border-color var(--dur-1) var(--ease-std),color var(--dur-1) var(--ease-std)}
button:hover:not(:disabled){background:var(--surface-hover)}
button:active:not(:disabled){background:var(--surface-pressed)}
button:disabled{background:var(--surface-panel);border-color:var(--line);color:var(--text-disabled);cursor:not-allowed}
button.active,button[aria-pressed=true]{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
button.primary{background:var(--accent);border-color:var(--accent);color:var(--text-on-accent);font-weight:var(--fw-semibold)}
button.primary:hover:not(:disabled){background:var(--accent-hover);border-color:var(--accent-hover)}
button.primary:disabled{background:var(--surface-sunken);border-color:var(--surface-sunken);color:var(--text-disabled)}
button.danger{color:var(--danger)}
button.danger:hover:not(:disabled){background:var(--danger-soft);border-color:var(--danger)}
button.stop-operation{background:var(--danger);border-color:var(--danger);color:#fff}   /* workspace.js beginStopOperation */
button.stop-operation:hover:not(:disabled){background:var(--danger-hover)}
button.ghost{background:transparent;border-color:transparent;color:var(--text-2)}
button.ghost:hover:not(:disabled){background:var(--surface-hover);color:var(--text)}
button.sm{min-height:var(--ctl-h-sm);padding:0 var(--sp-4);font-size:var(--fs-12)}
button.lg,#runAnalysis,#generateReport{min-height:var(--ctl-h-lg);padding:0 var(--sp-6)}
button.wide,.wide{width:100%}
:is(.icon-button,.icon-btn){width:var(--ctl-h);min-height:var(--ctl-h);padding:0;border-color:transparent;background:transparent;color:var(--text-2)}
:is(.icon-button,.icon-btn) svg{width:16px;height:16px}
.icon-btn:hover:not(:disabled){color:var(--danger);background:var(--danger-soft)}   /* row delete in Tubes */
button svg{flex:none;width:16px;height:16px;stroke:currentColor;fill:none;stroke-width:1.75;stroke-linecap:round;stroke-linejoin:round}
```

Rules:
- One `primary` per region: Run analysis, Add object, Save path, Use selected images, Add table, Save PDF + HWPX + Word, and the dialog confirm button.
- Button labels are verbs in sentence case (5.10). No trailing arrows.
- Busy: JS sets `disabled` through `controls()`. The status bar carries the busy state, so no per-button spinners.
- A danger button that fires immediately (Delete selected, Apply cut) stays outlined. Undo is the safety net, so there is no confirm dialog.

### 4.2 Segmented control (new: Tube measurement mode)

Used for Tube: **Length + Width / Length only / Width only**. It can also be used later for any 2–4-way exclusive choice. It is built from native radios, so arrow keys, form semantics and screen-reader announcements work without JS.

```html
<fieldset id="tubeMeasure" class="segmented">
  <legend>Measure</legend>
  <label><input type="radio" name="tubeMeasure" value="both" checked><span>Length + Width</span></label>
  <label><input type="radio" name="tubeMeasure" value="length"><span>Length only</span></label>
  <label><input type="radio" name="tubeMeasure" value="width"><span>Width only</span></label>
</fieldset>
```

```css
.segmented{display:inline-flex;align-items:center;gap:var(--sp-4);border:0;margin:0;padding:0;min-width:0}
.segmented legend{float:left;font-size:var(--fs-12);color:var(--text-3);padding:0;margin-right:var(--sp-4)}
.segmented>label{position:relative;display:inline-flex}
.segmented{--track:var(--surface-sunken)}
.segmented>label:first-of-type span{border-radius:var(--r-2) 0 0 var(--r-2)}
.segmented>label:last-of-type span{border-radius:0 var(--r-2) var(--r-2) 0}
.segmented input{position:absolute;opacity:0;inset:0;margin:0;cursor:pointer}
.segmented span{display:inline-flex;align-items:center;height:var(--ctl-h);padding:0 var(--sp-5);
  background:var(--track);border:var(--border-ctl);margin-left:-1px;font-size:var(--fs-12);color:var(--text-2);white-space:nowrap;
  transition:background-color var(--dur-2) var(--ease-std),color var(--dur-2) var(--ease-std)}
.segmented input:hover+span{color:var(--text)}
.segmented input:checked+span{background:var(--surface-raised);color:var(--accent);font-weight:var(--fw-semibold);border-color:var(--accent);position:relative;z-index:1;box-shadow:var(--shadow-1)}
.segmented input:focus-visible+span{outline:2px solid var(--focus);outline-offset:2px;z-index:2}
.segmented input:disabled+span{color:var(--text-disabled);cursor:not-allowed}
```

- Placement: in `#toolStrip`, right-aligned, visible only while `data-tool=tube`. `.ts-keys` move into the Tubes panel hint at widths below 1600 px, so the strip stays one line.
- Behavior: the choice persists for the session. It filters what the next trace measures. If the backend has no such option yet, the owner of `labimage.js`/`lab_editor.py` decides the API. This spec defines only the control and its ids. **If a control already exists under another id, keep that id and apply `class="segmented"`.**
- Table effect: hide the column that is not measured (`#tubeRows td:nth-child(2|3)`). Header copy is in 5.4.

### 4.3 Inputs, sliders, checkbox, select, color

```css
:is(input:not([type=checkbox],[type=radio],[type=range],[type=color],[type=file]),select,textarea){
  min-height:var(--ctl-h);padding:0 var(--sp-4);border:var(--border-ctl);border-radius:var(--r-2);
  background:var(--surface-raised);color:var(--text);font-size:var(--fs-13)}
textarea{padding:var(--sp-3) var(--sp-4);line-height:var(--lh);resize:vertical}
::placeholder{color:var(--text-3)}
:is(input,select,textarea):hover:not(:disabled){border-color:var(--text-3)}
:is(input,select,textarea):focus-visible{outline:2px solid var(--focus);outline-offset:0;border-color:var(--accent)}
:is(input,select,textarea)[aria-invalid=true],:is(input,select,textarea):user-invalid{border-color:var(--danger)}
:is(input,select,textarea):disabled{background:var(--surface-panel);color:var(--text-disabled);border-color:var(--line)}
input[type=number]{font-family:var(--font-mono)}
.field{display:block;margin:var(--sp-5) 0;font-size:var(--fs-12);color:var(--text-2)}
.field>:is(input,select,textarea){display:block;width:100%;margin-top:var(--sp-2)}
.field output{font-family:var(--font-mono);color:var(--text);margin-left:var(--sp-2)}
.two-fields{display:grid;grid-template-columns:1fr 1fr;gap:var(--sp-5)}
input[type=checkbox],input[type=radio]{width:16px;height:16px;margin:0 var(--sp-3) 0 0;vertical-align:-3px}
label:has(>input[type=checkbox]){display:inline-flex;align-items:center;min-height:var(--ctl-h-sm);font-size:var(--fs-13);color:var(--text)}
input[type=range]{height:var(--ctl-h-sm);width:96px;margin:0 var(--sp-2)}
input[type=color]{width:28px;height:var(--ctl-h-sm);padding:2px;border:var(--border-ctl);border-radius:var(--r-1);background:var(--surface-raised)}
input[type=file]{font-size:var(--fs-12)}
progress{width:100%;height:6px;accent-color:var(--accent)}
```

- Labels are always visible. A placeholder never stands in for a label (`#scalePixels` "Measure on image" is a hint inside a labeled field, which is fine).
- `role="switch"` on `#normalizeEnabled` stays a checkbox visually. No toggle-switch component is added.
- Field errors: put the message in the existing hint below the field (`#calibrationInfo`, `#minAreaInfo`) with `.error`, and set `aria-invalid`.

### 4.4 Panels and collapsibles

- **Inspector sections:** flat, as in 3.5.
- **Content panels** (Load, Setup, Report screens): `.panel{background:var(--surface-raised);border:var(--border);border-radius:var(--r-3);padding:var(--sp-6)}`, with no shadow. `.panel h2` is `--fs-14` semibold. Panels are never nested; `.report-card` inside `#reportComposer` uses a hairline only and no radius beyond `--r-2`.
- **Collapsible** (`labCollapsible()` in labimage.js; `.panel-collapsible`, `.ph-toggle`): keep the markup. `.ph-toggle` is a full-width, 32 px row, `--fs-14` semibold, with a 16 px chevron SVG at the right that rotates 0 to −90° in `--dur-2`. Hover is `--surface-hover`, and the focus ring is inside (`outline-offset:-2px`). Collapsed state hides `>:not(h2)`.
- **`<details>`** (More tools, Background & blur, Detection settings, Measurement definitions, Instrument and conditions): `summary` is the same 28 px row with a chevron, `list-style:none`, `--fs-13` `--text-2`, and `cursor:pointer`.

### 4.5 Tables

Covers `.results` (Tubes), `#poreTable` (Object details), `#detailsPlotStats`, and `.report-table-scroll table`.

```css
.table-wrap,.results-wrap,.details-table-wrap,.object-table-wrap{overflow:auto;border:var(--border);border-radius:var(--r-2);background:var(--surface-raised)}
:is(.results,#poreTable,#detailsPlotStats){width:100%;border-collapse:separate;border-spacing:0;font-size:var(--fs-13)}
:is(.results,#poreTable,#detailsPlotStats) th{position:sticky;top:0;z-index:var(--z-sticky);height:var(--row-h);padding:0 var(--sp-4);
  background:var(--surface-sunken);color:var(--text-2);font-size:var(--fs-12);font-weight:var(--fw-semibold);text-align:right;
  vertical-align:middle;border-bottom:var(--border);white-space:nowrap}
:is(.results,#poreTable,#detailsPlotStats) td{height:var(--row-h);padding:0 var(--sp-4);border-bottom:var(--border);text-align:right;
  font-family:var(--font-mono);white-space:nowrap}
:is(.results,#poreTable) :is(th,td):first-child{text-align:left}
:is(.results,#poreTable) tbody tr{cursor:pointer}
:is(.results,#poreTable) tbody tr:hover{background:var(--surface-hover)}
:is(.results,#poreTable) tbody tr:is(.selected,[aria-selected=true]){background:var(--accent-soft);box-shadow:inset 0 0 0 1px var(--accent)}
:is(.results,#poreTable) tbody tr:focus-visible{outline:2px solid var(--focus);outline-offset:-2px}
:is(.results tfoot,#poreDetailsStats) td{position:sticky;bottom:0;background:var(--surface-sunken);font-weight:var(--fw-semibold);border-top:var(--border-ctl);border-bottom:0}
#poreTable thead th[aria-sort]{color:var(--accent)}
```

**Tubes readout (`#tubeResults .results`)**: the signature element.
- Columns: ID | `T · Length (µm)` | `D · Width (µm)` | delete. Header copy is in 5.4; the header `T`/`D` are measure chips, not text with a dot.
- ID cell: two **measure chips** `T3` `D3` (4.7) followed by the source on a second line (`.src`, `--fs-11`, `--font-ui`, `--text-3`: "Ridge trace", "SAM mask", "Manual path"). Non-tube rows show `#3` in mono `--text-2`.
- Value cells: `.val` mono `--fs-13` semibold `--text`; `.none` `—` in `--text-3` with `aria-label="Not measured"`.
- Footer: `Mean ± SD (n = 3)` on the first cell, then mono values. With n = 1 it shows the mean only (current logic).
- Delete is a 24 px `.icon-btn` that shows on row hover and focus-within; it always stays reachable by keyboard.
- `tr.fresh` (new row): the background goes from `rgba(255,255,0,.35)` to transparent over 1.6 s. With reduced motion the row gets a static `rgba(255,255,0,.25)` until the next render (as today).
- `.results-wrap{max-height:320px}` at ≥ 1280 and 240 px below that.

**Object list in the Object details dialog (`#poreTable`)**: same rules. Sortable headers keep `.details-sort` and `aria-sort`; the sort direction icon is an SVG chevron, not a glyph.

### 4.6 Key caps (`kbd`, `.tk`)

```css
kbd,.tk{display:inline-grid;place-items:center;min-width:18px;height:18px;padding:0 var(--sp-2);
  font:var(--fw-semibold) var(--fs-11)/1 var(--font-ui);color:var(--text-2);background:var(--surface-raised);
  border:var(--border-ctl);border-bottom-width:2px;border-radius:var(--r-1);white-space:nowrap}
#tools .tk{position:absolute;top:3px;right:3px;height:16px;min-width:16px;font-size:10px} /* 10 px only inside the rail tile; it duplicates aria-keyshortcuts */
#tools button.active .tk{border-color:var(--accent);color:var(--accent)}
```

### 4.7 Chips

```css
.chip{display:inline-flex;align-items:center;height:20px;padding:0 var(--sp-3);border-radius:var(--r-1);
  font-size:var(--fs-11);font-weight:var(--fw-semibold);background:var(--surface-sunken);color:var(--text-2)}
.chip-measure{font-family:var(--font-mono);font-size:var(--fs-12);background:var(--measure);color:var(--measure-ink);border:1px solid var(--measure-edge)}
.chip-count,#tubeCount{font-family:var(--font-mono);background:var(--surface-sunken);color:var(--text);border-radius:var(--r-pill);padding:0 var(--sp-3);height:18px}
#tubeCount:empty,#tubeCount[data-n="0"]{display:none}
.chip-warn{background:var(--warn-soft);color:var(--warn)}
```

- `.chip-measure` is used only where the same label appears in yellow on the image: T#, D#, and the L/W path tags.
- `.report-source-chip` (report composer) uses `.chip` styling with a 24 px thumbnail and an icon close button.
- The `#tubeCalib` "not calibrated" button is styled as a `.chip-warn` button (28 px, left-aligned, warning icon).

### 4.8 Status, toasts, inline notices

- **Status bar:** 3.6. It is the single feedback channel for actions.
- **Inline status** (`#tubeStatus`, `#jobStatus`, `#measurementStatus`, `#reportPreviewStatus`, `#exportResult`): `--fs-12`. Neutral is `--text-2`, `.error` is `--danger`, success (`#exportResult`) is `--ok`. `#exportResult` stays selectable (`user-select:text`).
- **Notice** (`.notice`, `#legacyOverlap`, the `labRuntimeNotice` hint): `--warn-soft` background, `--warn` text, 1 px `--warn` border at 40 % (`color-mix(in srgb,var(--warn) 40%,transparent)`), radius `--r-2`, padding `var(--sp-4) var(--sp-5)`. No left bar.
- **Toast** (component defined, not used today): `position:fixed; right:var(--sp-6); bottom:calc(var(--status-h) + var(--sp-6)); z-index:var(--z-toast)`; `--surface-raised`, `--shadow-pop`, radius `--r-3`, max width 360 px, `role="status"`. It enters with opacity and 8 px translateY over `--dur-3` and auto-dismisses after 4 s on success. Use it only if a future action finishes while the user is on another screen; no toast is added in this redesign.

### 4.9 Dialogs

Covers `#poreDetailsDialog`, `#poreColumnsDialog`, `#reportAnalysesDialog`, `#reportContentsDialog`, `#reportTableDialog`, `#reportPlotDialog`, `#reportPdfDialog`, `#reportImageDialog` and `#feedbackDialog` (always hidden).

```css
dialog{padding:0;border:var(--border);border-radius:var(--r-4);background:var(--surface-raised);color:var(--text);box-shadow:var(--shadow-dialog);max-width:min(960px,calc(100vw - 32px))}
dialog::backdrop{background:var(--backdrop)}
dialog[open]{animation:dlgIn var(--dur-3) var(--ease-out)}
@keyframes dlgIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
dialog>h2,.details-titlebar,.columns-titlebar{display:flex;align-items:center;justify-content:space-between;min-height:44px;padding:0 var(--sp-4) 0 var(--sp-7);border-bottom:var(--border);font-size:var(--fs-16)}
dialog>:not(h2,.details-titlebar,.columns-titlebar){margin-inline:var(--sp-7)}
dialog .row:last-child{justify-content:flex-end;gap:var(--sp-4);padding:var(--sp-5) 0 var(--sp-6);margin-top:var(--sp-6);border-top:var(--border)}
```

- Close buttons (`#closePoreDetails`, `#closeColumns`, `#closeReportPdf`, `#closeReportImage`) become `.icon-button` with an X SVG and keep their `aria-label`. `#closeReportPdf` and `#closeReportImage` currently show the text "Close"; give them `aria-label="Close"` and use the icon.
- The footer order stays Cancel then primary, as in the current DOM. Changing it with CSS would break tab order.
- The Object details dialog keeps drag and resize (`.details-resize-*`). Its title bar is `--surface-panel` with `cursor:move`.
- `ui/details-window.html` must link `/theme.css` before `/workspace.css`. Its inline `<style>` stays (it only removes chrome).

### 4.10 Empty, busy, error and disabled states

| Area | Empty | Busy | Error | Disabled |
|---|---|---|---|---|
| Tubes panel `#tubeEmpty` | Line icon (tube SVG, `--text-3`) + **"No tubes measured yet."** + "Click both ends of a tube and LabImage traces and measures it, or switch Line to Manual and click along the tube. Right-drag a box across a tube for its width." + primary `Start tracing` with `kbd T` | Status bar busy. The table keeps its last rows; no skeleton (operations take under 1 s). | `#tubeStatus.error` above the table in `--danger`, plus the status bar | `#tubeStart` disabled until an image is open |
| Image library `#imageLibrary` | "No saved analyses yet. Open a new image to start." plus a ghost `New image` button that switches tabs | `#libraryStatus` "Loading saved analyses…" | `#libraryStatus.error` "Could not load saved analyses." + `#retryLibrary` "Try again" | none |
| Image well, no image | Not reachable (the editor needs `state`) | `aria-busy=true` on `#viewport` (already set) | status bar | none |
| Object details table | "No objects yet. Segment an object to see its measurements." | `#detailsSummary` "Updating…" | inline hint `.error` | none |
| Report composer `#reportContentCards` | "Choose images to start, or add a figure or table." (exists) | `#reportPreviewStatus` "Updating preview…" | `.error` hint next to the action | Add buttons disabled with no sources |
| Measurements `.metric` | `—` values | as above | as above | none |
| Rail tools | none | all disabled through `controls()` | none | `--text-disabled`, `cursor:not-allowed` |

Empty states show the next action. They never just say "nothing here".

### 4.11 Home screen (`#labHome`)

- Full-window overlay (`position:fixed; inset:0; z-index:var(--z-home)`), `--surface-app`. Content is left-aligned, `max-width:960px`, starting 18vh from the top, with padding `var(--sp-9)`.
- Title `h1` "LabImage" in `--font-display` `--fs-32` semibold. The lead paragraph is `--fs-14` `--text-2`, max 60ch: **"Choose a workspace. Both run on this computer with the SAM 2.1 Small model."**
- Two mode cards in a `grid-template-columns:1fr 1fr; gap:var(--sp-6)` grid. Each is the existing `<button>`, styled: `--surface-raised`, `--border`, radius `--r-4`, padding `var(--sp-8)`, min-height 220 px, left-aligned column flex, `gap:var(--sp-4)`. Hover: border `--accent`. Focus: global ring. Active: `--surface-pressed`.
- Card content (inline elements only, valid inside `<button>`):
  - A 48 px line schematic (inline SVG, `--text-2` strokes). Labeling: three outlined blobs with small ID numbers. Report: a gray curved tube with a pure-yellow `--measure` segment and a black-on-yellow `T1` chip. This is the only place outside the image where yellow appears in chrome, as a preview of the readout.
  - `strong` name (`--fs-20`): "Labeling" / "Report".
  - `span` description (`--text-2`).
  - `small` outputs line (`--text-3`, `--fs-12`).
  - `b` action text in `--accent` semibold: "Start labeling" / "Start a report", with no arrow.
- `.lab-home-foot`: "Runs offline with the official SAM 2.1 Small model. No fine-tuning." in `--fs-12` `--text-3`.
- Below 760 px the cards stack in one column.

### 4.12 Icons

One inline-SVG set: 24-unit viewBox, `fill:none`, `stroke:currentColor`, stroke width 1.75, round caps and joins. The existing `ICON` map in `labimage.js` is the source. Add these keys to it and reuse them from other files through a small `window.labIcon(name)` helper, or inline the paths:

| Key | Use | Replaces |
|---|---|---|
| `close` (two diagonals) | dialog close, chip remove | `×`, `\u00d7` |
| `external` (box + arrow) | `#openPoreDetails` | `↗` |
| `refresh` (existing path in `#refreshMeasurements`) | `#loadReportContent`, `#refreshReportPreview` | `↻` (`&#8635;`) |
| `grip` (2×3 dots) | `.report-drag-handle` | `☰` |
| `plus` | Add figure, Add table, Add plot, Add row | `+ ` text prefix |
| `upload` (tray + up arrow) | `.upload-icon` | `＋` |
| `chevron` | collapsibles, `<summary>`, sort direction | CSS borders, `▲▼` |
| `warning` | `#tubeCalib`, notices | none |
| `save` (tray + down arrow) | `#saveEditorImages` | none |

Every icon is `aria-hidden="true"`. Icon-only buttons keep or get an `aria-label`.

---

## 5. Per-screen mapping

The ids, `data-*` attributes and class names listed here are used by JS or tests. **Keep them all.** "Change" means styling or copy only, unless it says *DOM*.

### 5.1 Global chrome

| Element | Ids/classes (keep) | Change | Copy |
|---|---|---|---|
| Header | `header`, `.app-brand h1`, `.app-brand span`, `#labModeBadge`, `#labHomeButton`, `#openFeedback` (hidden) | 48 px row with the stepper inside (3.1). The badge becomes plain text. | h1 "LabImage". Engine span: initial "SAM 2.1", then "SAM 2.1 on CPU" / "SAM 2.1 on Intel GPU". Badge: "Labeling" / "Report". Home button: **"Workspaces"**, `title="Switch workspace"`. |
| Stepper | `nav.steps`, `button[data-panel=load|setup|editor|analysis]`, `.active`, `aria-current` | *DOM:* moved into the header. The number gets `<b class="step-n">`. | Report: "Load image", "Set scale", "Segment and measure", "Build report". Labeling: "Load image", "Set up", "Label and refine" (step 4 is hidden). |
| Status bar | `#status` (`role=status`), `.error`, `body.is-busy` | 3.6 | Unchanged except the strings in 5.10. |
| Home | `#labHome`, `.hidden`, `.lab-home-inner`, `.lab-mode-cards`, `#labChooseLabel`, `#labChooseReport`, `.lab-home-foot` | 4.11. Delete `.lab-eyebrow`, `.lab-card-index` and `.lab-home-lead` styling (`.lab-home-lead` is kept as the lead paragraph). | Labeling card: name "Labeling"; description "Segment every object automatically, correct it with points, and export instance masks."; outputs "16-bit PNG masks, NumPy arrays and metadata"; action "Start labeling". Report card: name "Report"; description "Segment objects with prompts, measure lengths and widths, and build a report."; outputs "Measurement figure, CSV, and PDF, HWPX and Word reports"; action "Start a report". |

### 5.2 Step 1: Load image (`#loadPanel`, both modes)

| Element | Ids/classes | Change | Copy |
|---|---|---|---|
| Title | `.workspace-intro h2` | `--fs-20`, left-aligned, `max-width:1200px` content column, padding `var(--sp-8)` | "Load image" |
| Tabs | `.load-tabs`, `#newImageTab`, `#openAnalysisTab`, `role=tab`, `aria-selected`, `.active` | Underline tabs: 36 px, `--text-2`. Selected is `--text` semibold with a 2 px `--accent` *bottom* border (allowed; it is not a side border). | "New image", "Open analysis" |
| Upload | `#newImagePane`, `.import-panel`, `.upload-zone`, `#uploadFile`, `.upload-icon`, `#imageSelectionStatus` | Dashed `--line-strong` 1 px border, `--surface-raised`, radius `--r-3`, 160 px tall. Hover and `:focus-within`: `--accent` border with `--accent-soft` fill. Upload SVG icon. | h2 "Import an image". Strong "Choose image". Span "TIF, PNG or JPG, up to 32 MB" |
| Library | `#savedImagePane`, `.image-library`, `#libraryStatus`, `#retryLibrary`, `#imageLibrary`, `.image-cards`, `.image-card[data-image-id][data-analyzed]`, `.image-action` | Grid `repeat(auto-fill,minmax(200px,1fr))`, gap `--sp-5`. Card: `--surface-raised`, `--border`, `--r-3`, padding `--sp-4`. Thumbnail: 4:3 on `--well`, `object-fit:contain`. Hover: `--accent` border. | Action: "Open analysis" (workspace.js; the arrow is removed). Empty and error copy are in 4.10. |

### 5.3 Step 2: Set scale / Set up (`#setupPanel`)

| Element | Ids/classes | Change | Copy |
|---|---|---|---|
| Title | `#setupPanel .workspace-intro h2` | as 5.2 | Report: "Image and scale". Labeling: "Labeling setup" |
| Layout | `#newAnalysisSettings`, `.setup-grid` | `grid-template-columns:minmax(0,1fr) 340px; gap:var(--sp-6)`. One column below 1000 px. | none |
| Preview | `.setup-preview`, `#setupImageTitle`, `#imageDetails`, `.setup-canvas-wrap`, `#setupCanvas`, `#measureScale` | Content panel. Canvas wrap on `--well`, radius `--r-2`. `#imageDetails` in mono `--fs-12` `--text-3`. | `#setupImageTitle` is the file name (set by JS). `#imageDetails`: "1024 × 946 px, 8-bit. Bottom information strip excluded (178 px)." (workspace.js and labimage.js; commas replace the dots). `#measureScale` "Measure scale bar", `title="Click both ends of the scale bar"`. |
| Processed preview (Labeling only) | `#preprocessingImage` section (`.lab-label-only`), `#preprocessingInfo` | Content panel | h2 "Processed preview" |
| Calibration | `#labCalibrated`, `.lab-calibration-toggle`, `#regionSettings` (labeling only), `#analysisBottom`, `#bottomSlider`, `#scaleUm`, `#scalePixels`, `#calibrationInfo`, `#scaleConfirmed` | Content panel. Fields as in 4.3. | h2 "Calibration". Hint: "Measure in pixels, or calibrate against a known distance." Checkbox: "Calibrate in micrometres (µm)". Fields: "Scale length (µm)", "Scale length (px)" with placeholder "Measure on the image". `#calibrationInfo` uncalibrated: "Pixel units. No physical calibration." Checkbox: "Confirm calibration". `#regionSettings` summary: "Analysis region"; field "Bottom boundary (px)". |
| Image processing (Labeling only) | `#normalizeEnabled` section (`.lab-label-only`), `#optionalProcessing`, `#optionalProcessingStatus`, `#backgroundStrength`, `#backgroundValue`, `#backgroundHelp`, `#blurMethod`, `#blurHelp`, `#blurStrengthField`, `#blurStrength`, `#blurValue` | Content panel. The smoke test needs this section at `display:none` in Report: keep `.lab-label-only`. | h2 "Image processing". "Brightness normalization". Summary "Background and blur". The rest is unchanged. |
| Detection (Labeling only) | `#advancedSettings`, `#minContrast` (hidden), `#minArea`, `#minAreaInfo`, `#pointDensity`, `#resetCriteria`, `.lab-inactive-detection` | `<details>` content panel | Summary "Detection settings". "Minimum area (px²)". "Sampling". `#resetCriteria` "Reset to defaults". |
| Start | `.analysis-start`, `#runAnalysis`, `#analysisSettingsSummary`, `#analysisProgress`, `#jobStatus` | Primary `lg` button, full width. `progress` 6 px. | `#runAnalysis`: Labeling "Run automatic labeling"; Report "Open measurement workspace". Stop state: "Stop" / "Stopping…" (workspace.js, unchanged). `#jobStatus` when not confirmed: "Confirm the calibration to continue." |

### 5.4 Step 3: Editor (`#editorPanel`), shared parts

| Element | Ids/classes | Change | Copy |
|---|---|---|---|
| Document bar | `.document-toolbar`, `#editorImageName`, `#dataset` (hidden), `#saveEditorImages`, `#fitComparison`, `#zoom`, `#zoomLabel`, `#showOverlay`, `#poreColor`, `#poreOpacity`, `#poreOpacityValue`, `#showPoreLabels` | 40 px, `--surface-panel`, `border-bottom:var(--border)`, `flex-wrap:nowrap`, gap `--sp-5`. The name is semibold with ellipsis and `title`. The values (`#zoomLabel`, `#poreOpacityValue`) are mono, min-width 4ch. `#saveEditorImages` is secondary with the save icon. | Name: the file name. `#saveEditorImages`: **"Save images"**, `title`: Labeling "Export instance masks to a folder", Report "Export the measurement figure and CSV to a folder". `#fitComparison` "Fit". Labels "Zoom", "Objects", "Opacity", "IDs". `#poreColor` `aria-label="Object color"`. |
| Rail | `#tools`, `.tool-group`, `[data-mode=select|tube|positive|prompt-positive|negative|box|polygon|ellipse|cut|delete]`, `#back`, `#clear`, `.tool-sep`, `.ti`, `.tl`, `.tk`, `#tubeTool` (`.lab-report-only`) | **JS:** `labRailRender` renders icons for **both** modes, and `labRailOrder(true)` runs for both. Tube stays report-only through its class. `ellipse`/`cut` stay hidden without `body.lab-advanced`. | Names and tooltips from `TOOL_UI`, with Korean removed (5.9). Tool names: Select, Tube, Add, Point +, Point −, Box, Polygon, Ellipse, Cut, Delete, Undo, Clear. |
| Tool strip | `#toolStrip`, `.ts-name`, `#tsName`, `#tsText`, `#tsSteps` (`li[data-step]`, `.now`, `.done`), `#tsKeys`, `.ts-count` | **JS:** remove `lab-report-only` from `#toolStrip`, and remove the `labMode!=='report'` early return in `labStrip()`, so `body[data-tool]` is set in both modes. 40 px fixed, `--surface-panel`, `border-bottom:var(--border)`, one line. Steps: 20 px number circles. `.now` is filled `--accent`; `.done` is a `--ok` outline with a check icon in place of the number. The connector is 16 × 1 px `--line-strong`. `.ts-count` is mono `--text`; cyan is never used for text. | Per `TOOL_UI.text`. Tube steps: "Click one end", "Shift-click to add bends (optional)", "Click the other end". `.ts-count`: "2 points". Key labels: "bend", "finish", "remove point", "cancel", "segment with SAM". |
| Tube mode control | `#tubeMeasure` (4.2; new, or the existing id) | In the strip, right side, Tube only | Legend "Measure". Options "Length + Width", "Length only", "Width only". |
| Selection actions | `#selectionActions`, `#selectBoundaryPores`, `#mergePores`, `#selectedPoreCount` | In the strip cell (3.2), small buttons. The count is mono `--accent`. | "Select boundary objects", "Merge selected", "0 selected" (JS). |
| Panes | `.comparison-viewports`, `.comparison-pane`, `#originalViewport`, `#originalImage`, `#viewport`, `#image`, `.comparison-cursor-overlay` | 3.4. The comparison crosshair color in comparison.js (`#000`/`#fff`) stays. | "Original", "Segmentation" |
| Legend | `.legend`, `#poreLegendDot`, `#supplementalLegendDot`, `.dot` (inline data colors stay) | 24 px, `--fs-12`, `--text-3`, padding `0 var(--sp-5)` | "Objects", "Added", "Preview", "Replaced objects" |
| Overlap notice | `#legacyOverlap`, `#legacyOverlapText`, `#resolveOverlaps` | Notice (4.8) | "This analysis has N overlapping pixels." Button "Resolve overlaps". |

### 5.5 Inspector: shared panels

| Panel | Ids/classes | Copy |
|---|---|---|
| Segment (`.lab-controls`, injected) | `#labAutoCommit`, `#labNewObject`, `#labPromptStatus`, `#labAdvancedTools`, `body.lab-advanced`; runtime notice `<p class="hint" role="status">` | h2 **"Segment"**. Hint: "Click inside an object to segment it. Shift-click refines; right-click excludes." Checkbox: "Apply point edits immediately". `#labNewObject`: **"New object"**, `title="Clear the prompts and start a new object (Esc)"`. `#labPromptStatus` initial: "Start with a point. Use Box when points are not enough." In-session: "Object #12, 3 prompts" or "New object, 1 prompt". `<details>` summary "More tools"; hint "Ellipse and cut tools, for hard cases."; `#labAdvancedTools` "Show ellipse and cut" with `aria-pressed`, toggling to "Hide ellipse and cut". The runtime notice uses the notice style. |
| Region preview (`#regionPanel`) | `#toolHint`, `#target`, `#predict`, `#regionQueue`, `#finishRegion`, `#updateRegionPreview`, `#regionQueueList`, `.queued-region` | h2: Labeling "Segment", Report "Region preview" (current JS; keep). "Target" label. `#target` first option "New object"; other options "#12, 34.5 µm²" (editor.html `accept()`). `#predict` "Preview" / "Preview polygon". `#finishRegion` "Finish region", `#updateRegionPreview` "Update preview", `.queued-region` rows are list rows with 28 px height. |
| Preview (`#previewPanel`) | `#previewControls`, `#choices` (buttons `.active`), `#previewInfo`, `#overlap`, `#trimOverlap`, `#apply`, `#skipRegion`, `.edit-actions`, `#delete` | h2 "Preview". Choices "Option 1/2/3" as a `.segmented`-looking button row (buttons with `.active`; they stay buttons). `#previewInfo` "Area 12.34 µm²" (mono value). `#overlap` in the warn color. `#trimOverlap` "Trim overlap". `#apply`: primary "Add object" / "Replace object" / "Replace N objects". `#skipRegion` "Skip". `#delete`: danger "Delete selected". |
| Object details (`#poreListPanel`) | `#openPoreDetails` | Secondary, wide, external icon. Copy **"Open object details"** (the `↗` is removed). |
| Cut (`#cutPanel`, advanced) | `#cutSettings`, `#cutWidth`, `#cutWidthValue`, `#applyCut`, `#cutStatus` | h2 "Cut". "Width (px)". `#applyCut` danger "Apply cut" / "Apply cuts (3)". |
| Automate | `.automate-panel`, `#automatePores` | Stays hidden (`labimage.css`). |

### 5.6 Inspector: Report-only panels

| Panel | Ids/classes | Change | Copy |
|---|---|---|---|
| Tubes (`#tubePanel`) | `.panel-head`, `#tubeCount`, `#tubeUndo`, `#tubeStatus`, `#tubeCalib`, `#tubeEmpty`, `#tubeStart`, `#tubeResults`, `.results-wrap`, `.results`, `#tubeLenHead`, `#tubeWidHead`, `#tubeRows` (`tr[data-id]`, `.selected`, `.fresh`, `aria-selected`), `#tubeFoot`, `#tubeHint`, `.src`, `.val`, `.none`, `.icon-btn` | First section. The gradient is removed. Table and chips as in 4.5 and 4.7. `#tubeUndo` is `.sm` secondary. | h2 "Tubes" + count chip. `#tubeUndo` "Undo" with `title="Undo the last point or saved edit (Ctrl+Z)"`. `#tubeCalib`: "Lengths are in pixels. Set the scale" (warning chip). `#tubeStatus` while tracing: "Tracing: 2 points. Click the other end, Shift-click to add a bend, or press Enter to finish." Headers (JS `tubeRender`): with tubes, chip `T` + "Length (µm)" and chip `D` + "Width (µm)"; without tubes, "Length (µm)" / "Width (µm)". Rows: chips `T3` `D3` (JS: build two `span.chip.chip-measure`, not the string "T3 · D3"). Footer "Mean ± SD (n = 3)". `#tubeHint`: "**T#** on the image is a tube's length and **D#** its width. Click a row to select the tube. Ctrl-click a tube on the image to segment it with SAM. Ctrl+Z undoes the last saved tube." Delete `aria-label="Delete tube 3"`, `title="Delete #3 (Ctrl+Z restores it)"`. |
| Measurements (`.panel:has(.metric)`, `.lab-report-only`) | `#refreshMeasurements` (`.icon-button`), `#measurementStatus`, `.metric`, `#count`, `#fraction`, `#diameter`, `#edge`, `#area`, `#hist` | `.metric` is a 2×2 grid of label/value pairs (no tiles): `small` `--fs-12` `--text-3`, `b` mono `--fs-16`. Hairline between rows. The histogram reads `--chart-bar`/`--chart-axis`. | h2 "Measurements". Labels "Object count", "Area fraction (2D)", "Median diameter (µm) †", "Boundary objects". `#area`: "Image area 1234.5 µm², object area 56.7 µm²". Stale: "Objects changed. Refresh to update." Second heading "Diameter distribution". |
| Endpoint measurements (`#manualPanel`, collapsible) | `#manualObject`, `#manualAutomatic`, `#manualAxis`, `#manualStyle`, `#manualStart` (`.active`), `#manualHint`, `#manualSave`, `#manualBack`, `#manualCancel`, `#manualValue`, `.manual-value` | Flat section. `.manual-value` is mono `--text`, with a `.chip-measure` L or W prefix. | h2 "Endpoint measurements". Hint: "LabImage places the center point automatically. Mark both ends of L and W; each path runs through that center inside the object. Labels are drawn outside the object." Options: "L, longitudinal" / "W, transverse"; "Through center (2 points)", "Draw a curve", "Click curve points". `#manualStart` "Set endpoints". `#manualAutomatic` "Clear saved measurements". Buttons "Save path", "Undo point", "Cancel". `#manualValue`: "No path yet" / "Ready to trace through the object" / "123.45 px along the drawn path, 12 points". |
| Figure appearance (`#labMeasurementSettings`, collapsible, collapsed) | `#labShowMeasurements`, `#labShowLength`, `#labShowWidth`, `#labFontSize` | Flat section | h2 "Figure appearance". "Show measurement paths and labels", "L, longitudinal path", "W, transverse path", "Label size (image px)". Hint: "Measure each axis with two endpoints. Values stay blank until measured. Area and perimeter are in Object details." |

Tube line modes (replaces drag tracing and its live preview, 2026-11-10): a **Line** segmented control (Auto | Manual) sits after Measure and is hidden in Width only. Auto: click both ends, Shift-click bends, the ridge is traced. Manual: every click is a vertex; the pending line is drawn in measurement yellow `#ffff00`, straight between clicks; clicking the last point again or Enter saves it unchanged (`trace-tube` with `manual:true`). A left drag does nothing; the right-drag D box stays.

Particle tool (2026-11-11, docs/particle-design.md): rail tile **Particle** (`P`, Report only, after Tube). The strip shows **Mode** (Detect | Click | Line, remembered in `labimage.particleMode`); Detect adds a primary `Detect particles` button, Line adds **Measure** (Length | Width), which switches to Width after a length line is saved and back to Length after a width line. Detect sends `detect-particles`, Click sends `measure-particle {point}`, Line sends `particle-line {axis, points}` on release (or on the second click); `Backspace`, `Esc` or `Ctrl+Z` remove the pending first point; a right drag does nothing. Results share `#tubePanel`: in the Particle tool its heading reads "Particles" and its empty state, mode hint and key hint are particle copy (`.particle-only` / `.tube-only`, toggled by `body[data-tool]`). Particle rows show `#id` (the figure labels are value-only) with a source tag Auto, Click or Manual line, else Particle. Like Tube, the tool hides the Original pane and the shape panels.

### 5.7 Step 4: Build report (`#analysisPanel`, Report only)

| Element | Ids/classes | Change | Copy |
|---|---|---|---|
| Header | `#analysisTitle`, `#analysisSubtitle`, `#editFromAnalysis`, `#settingsFromAnalysis` | Title `--fs-20`. The buttons are ghost buttons with a back chevron. | "Build report". `#editFromAnalysis` "Back to measurements". `#settingsFromAnalysis` **"Image and scale"** (workspace.js sets this text; change it there). |
| Composer | `#reportComposer.report-simple`, `.report-main-toolbar`, `#addReportAnalyses` (primary), `#addReportFolders`, `#reportSourcesStatus`, `#reportMore`, `.report-more-menu`, `#reportWorkspaceSelect`, `#newReportWorkspace`, `#saveReportDraft`, `#reportSourceChips`, `.report-source-chip`, `.report-title-row`, `#reportTitle`, `#reportDraftStatus` | Content panel. The title input is borderless until hover/focus, `--fs-20`. The "More" menu is a popover (`--shadow-pop`, `--z-popover`). | "Choose images", "Add folders", "Select images for your report." More menu: "Open report", "New report", "Save draft". Title placeholder "Report title". |
| Editor tabs | `#reportComposeBody`, `.report-layout`, `.report-editor-tabs`, `#reportContentTab`, `#reportTextTab` | Underline tabs (as 5.2) | "Figures and tables", "Text and conditions" |
| Text fields | `#reportTextFields`, `#reportConditions`, `.report-condition`, `#addReportCondition`, `#setReportConditionsDefault`, `#reportConditionsDefaultStatus`, `#reportMethod`, `#reportResults`, `#refreshReportSummary`, `#reportSummaryStatus` | Fields as in 4.3 | Summary "Instrument and conditions"; hint under it "Enter these manually." "Add row" (plus icon), "Save as default". Labels: "Analysis method" with hint "Enter manually."; "Results" with hint "Editable draft." `#refreshReportSummary` "Regenerate draft". |
| Assets | `#reportAssetFields`, `#addReportFigure`, `#addReportTable`, `#addReportPlot`, `#reportContentCards`, `.report-cards`, `.report-card`, `.report-drag-handle`, `.report-panels`, `.report-panel-row`, `.report-panel-image`, `.report-remove-*`, `.report-new-row`, `.drag-over`, `.dragging` | Cards: `--surface-raised`, hairline, `--r-2`. The drag handle is a grip SVG; `cursor:grab`. Drop target: 2 px dashed `--accent` outline. | "Add figure", "Add table", "Add plot" (plus icon). "Drag images to place them side by side or one below the other." `.report-new-row` "Drop here to add a row". |
| Preview | `.report-preview`, `.report-preview-toolbar`, `#previewReportPdf`, `#loadReportContent`, `#refreshReportPreview`, `#reportPreviewStatus`, `#composedReportPreview` | The iframe stays white (a document page) with a `--border` and `--shadow-1`. Refresh buttons are icon buttons. | h "Preview". "Preview PDF". `#loadReportContent` `aria-label="Update analysis content"`. |
| Export | `.export-panel`, `#exportDirectory`, `#chooseExportDirectory`, `#reportFileName`, `#reportFileNameHint`, `#generateReport`, `#reportGenerationStatus`, `#exportResult`, `#analysisDownloads`, `.download-links` | Content panel | h2 "Save report". "Destination folder"; placeholder "Full folder path". "Browse…". "File name"; hint "PDF, HWPX and Word extensions are added automatically." `#generateReport` primary "Save PDF, HWPX and Word". Success: "Saved to C:\…" (mono path). |
| Legacy | `#analysisFrame`, `#analysisComparison` | No change | none |
| Dialogs | `#reportAnalysesDialog` (`#selectAllReportAnalyses`, `#clearReportAnalyses`, `#reportAnalysesChoices`, `#reportAnalysesError`, `#cancelReportAnalyses`, `#applyReportAnalyses`); `#reportContentsDialog`; `#reportTableDialog` (all `reportTable*` ids); `#reportPlotDialog` (all `reportPlot*` ids); `#reportPdfDialog`; `#reportImageDialog` | 4.9 | Titles: "Choose images", "Add contents", "Add table", "Add plot", "PDF preview". Buttons: "Select all", "Clear", "Cancel", "Use selected images", "Apply", "Add table", "Preview", "Add to figure". Table types "Size statistics", "Analysis summary"; "Decimal places". Plot types "Histogram", "Scatter plot"; "Maximum bins"; "X axis", "Y axis"; "Exclude boundary objects". |

### 5.8 Object details (dialog and separate window)

| Element | Ids/classes | Change | Copy |
|---|---|---|---|
| Title bar | `#poreDetailsDialog`, `#poreDetailsHandle.details-titlebar`, `#poreDetailsTitle`, `#closePoreDetails` | 4.9; close is an X icon | "Object details". Stale: "Object details: refresh to update" (object-details.js; the `·` is removed). |
| Tabs | `.details-toolbar[role=tablist]`, `#detailsTableTab`, `#detailsHistogramTab`, `#detailsScatterTab` (`data-detail-view`), `#downloadDetails`, `#downloadPlot`, `#openDetailsColumns` | Underline tabs. Export buttons are secondary on the right. The columns button is an icon button with `aria-label="Choose columns"`. | "Table", "Histogram", "Scatter plot"; "Export CSV", "Export plot" |
| Target picker | `#detailsTargetPicker`, `#detailsTargetCount`, `.target-popover`, `#detailsSelectAll`, `#detailsSelectNone`, `#detailsTargetSearch`, `#detailsTargetOptions`, `#detailsSummary` | Popover (`--shadow-pop`, `--z-popover`, `position:fixed` if clipped) | "Objects (2 of 2)", "Select all", "Clear", placeholder "Search by ID". `#detailsSummary`: "2 selected. Image area fraction (2D): 2.364 %". |
| Table and plot | `#poreTable`, `#poreListRows`, `#poreDetailsStats`, `.stat-label`, `.details-sort`, `#detailsPlotView`, `#detailsXAxis`, `#detailsYAxis`, `#detailsBins`, `#detailsPlot`, `#detailsPlotInfo`, `#detailsPlotStats` | 4.5. The plot canvas stays white. object-details.js chart colors may switch to the tokens (optional). | Headers unchanged except the broken title `Object area / analysis area ? 100` → `Object area / analysis area × 100`. "Maximum bins". |
| Footer | `#poreSelectionInfo`, `#clearPoreSelection`, `.details-definitions` | Ghost button | "No selection", "Clear selection". Summary "Measurement definitions" (text unchanged). |
| Columns dialog | `#poreColumnsDialog`, `.columns-titlebar`, `#columnsTitle`, `#closeColumns`, `.columns-lists`, `#columnDescription` | 4.9 | "Columns" |
| Separate window | `ui/details-window.html` | *DOM:* add `<link rel="stylesheet" href="/theme.css">` before workspace.css | Title "Object details" |

### 5.9 Korean text to remove (all in `ui/labimage.js`)

Grep for the strings; the line numbers move.

| Where | Current | Replace with |
|---|---|---|
| `TOOL_UI.tube.tip` | `'Measure a tube: click both ends. ' + Korean sentence` | `'Measure a tube: click both ends.'` |
| `toolStrip.innerHTML`, 3× `<small lang="ko">…</small>` | Korean step glosses | Delete the three `<small lang="ko">` elements. Step 2 keeps `<small>optional</small>`. |
| `tubePanel.innerHTML` h2 | `Tubes <span lang="ko" class="ko">…</span>` | `Tubes` |
| `#tubeCalib` | `Not calibrated · Set scale / <span lang="ko">…</span>` | `Lengths are in pixels. Set the scale` |
| `#tubeEmpty` | `<span lang="ko" class="ko">…</span>` after the strong | Delete it. Copy as in 4.10. |
| `#tubeHint` | `<br><span lang="ko">…</span>` | Delete it. Copy as in 5.6. |
| CSS | `.ko{…}`, `small[lang=ko]` media rule (report-ui.css) | Deleted together with report-ui.css |

Verification (must print nothing):
`python -c "import re,glob;[print(f,i) for f in glob.glob('ui/*.*') if f.endswith(('.js','.html','.css')) for i,l in enumerate(open(f,encoding='utf-8'),1) if re.search('[\uac00-\ud7a3]',l)]"`

### 5.10 Copy rules and the remaining strings

Rules: sentence case; verbs name the action; the same action keeps the same word everywhere ("Save images" produces "Images saved to …"); no middle-dot joins, no trailing arrows, no apologies; errors say what happened and what to do next.

Strings with ` · ` to rewrite (grep `" · "` in `ui/*.js ui/*.html`):

| Current | New |
|---|---|
| `SAM 2.1 · Segment, measure, export` | `SAM 2.1` |
| `Intel GPU · SAM 2.1` / `CPU · SAM 2.1` | `SAM 2.1 on Intel GPU` / `SAM 2.1 on CPU` |
| `Labeling · Instance masks` / `Report · Measurements` | `Labeling` / `Report` |
| `Save Images · Instance masks` / `· Measurement figure` | `Save images` (the difference moves into `title`) |
| `Pixel units · No physical calibration` | `Pixel units. No physical calibration.` |
| `… · Bottom information strip excluded (N px)` | `…. Bottom information strip excluded (N px).` |
| `Object #N · K prompts` / `New object · K prompts` | `Object #N, K prompts` / `New object, K prompts` |
| `Applied · Shift-click to refine · Right-click to exclude · Ctrl+Z to undo` | `Applied. Shift-click to refine, right-click to exclude, Ctrl+Z to undo.` |
| `Preview · Refine with points, then press Enter or Add Object.` | `Preview ready. Refine with points, then press Enter or Add object.` |
| `L · Longitudinal (path)` / `W · Transverse (path)` | `L, longitudinal (path)` / `W, transverse (path)` |
| `N px along drawn path · K points` | `N px along the drawn path, K points` |
| `Tracing · N points. …` | `Tracing: N points. …` (5.6) |
| `tubeSummary`: `L 12.34 µm · W 1.23 µm` | `L 12.34 µm, W 1.23 µm` |
| `Traced object #N · {summary} · Ctrl+Z to undo` | `Traced object #N: {summary}. Ctrl+Z to undo.` |
| `Measured object #N from SAM mask · {summary} · Ctrl+Z twice removes it` | `Measured object #N from its SAM mask: {summary}. Press Ctrl+Z twice to remove it.` |
| `T · Length` / `D · Width` headers, `T3 · D3` cells | Chips (5.6) |
| `Mean ± SD · n=3` | `Mean ± SD (n = 3)` |
| workspace.js `… µm · Image area …`, `px · … · 8-bit preview`, `Normalization … · Background …` | Same content joined with commas, ending with a period. |
| `Merging objects?` (editor.html, a typo) | `Merging objects…` |
| `Export cancelled` | `Export cancelled.` |
| `Cannot connect to server: …` | `Cannot reach the LabImage engine: …. Restart LabImage.` |
| Title Case buttons not listed above (`Undo Input`, `Clear Input`, `Select Boundary Objects`, `Merge Selected`, `Delete Selected`, `Add Object`, `Finish Region`, `Update Preview`, `Trim Overlap`, `Resolve Overlaps`, `Reset Defaults`, `Run Analysis`, `Export CSV` stays) | Sentence case: `Undo input`, `Clear input`, … |

Out of scope: report document content (inside the iframe and the exported files) and server error messages.

---

## 6. Migration plan

**Ownership.** `ui/labimage.js` and `scripts/` are being edited by another agent. Do the CSS and HTML steps (1–4, 6) any time. Do the JS step (5) after that agent finishes, or hand it the 5.x list as a patch request. Do not edit `scripts/lab_ui_smoke.py` while it is owned elsewhere; section 6.3 lists proposed additions.

### 6.1 What gets replaced

| Source | Fate |
|---|---|
| `ui/report-ui.css` (25 KB, dark, scoped to `body[data-lab-mode=report]`) | **Deleted.** Its layout rules (editor grid, rail, strip, inspector order, Tube single pane, Tubes table, collapsible, responsive) move to `workspace.css` without the mode scope, rewritten with tokens. Its colors, `color-scheme:dark`, `html:has(...)` background, `.ko`, gradients and 3 px inset bars are dropped. |
| `ui/workspace.css` (37 KB, light, raw hex: about 24× `#cbd5e1`, 21× `#2563eb`, …) | **Kept as the layout and screen file.** The `:root` font and color line, the base `button`/`select`/`input`/`.panel`/`.toolbar`/`.status`/`.hint` rules and all hex colors are replaced by tokens or removed (they live in theme.css). The screen-specific layout (setup grid, report composer, details dialog sizing, columns dialog) stays. `.edit-tools`/`.tool-group` horizontal-toolbar styling is replaced by the rail. |
| `ui/labimage.css` (3 KB) | **Reduced to mode rules and home layout:** `body[data-lab-mode=labeling] [data-panel=analysis]`, `.lab-report-only`, `.lab-label-only`, `body:not(.lab-advanced) [data-mode=ellipse|cut]`, `.lab-inactive-detection,.automate-panel,#feedbackDialog{display:none!important}`, `.tool-group:empty`, and the home grid. All colors go (`#101b29`, `#1b2b3d`, `#6ed5be`, `#labHomeButton` hack, `#manualPanel` yellow). |
| Inline `<style>` in `details-window.html` | Kept (it only removes chrome). theme.css is added before it. |
| Inline `style=` in `editor.html` (legend dots) and `.style.background` in `comparison.js` | Kept: data colors. |
| Canvas colors in JS (`#ffd372` drafts, `#65ff9a`/`#ff7171` prompt points, `rgba(6,8,12,…)` trace halo) | Kept: image domain. Exception: `drawManualMeasurement` uses `#ffed00`; change it to read `--measure` (pure `#ffff00`) like `traceColor()` reads `--trace`. |
| `object-details.js` plot colors (`#334155`, `#e2e8f0`, `#64748b`) | Optional: read `--text-2`, `--line`, `--text-3`. It already looks right on light. |
| Unicode glyph icons (`＋`, `↗`, `↻`, `☰`, `×`, `→`, `▲▼`) | SVG (4.12). |

### 6.2 Steps (each one can be checked on its own)

1. **Add `ui/theme.css`** with sections 2 and 2.1 and components 4.1–4.12. Link it first in `editor.html` (`<link rel="stylesheet" href="/theme.css">` before workspace.css) and in `details-window.html`. Check that the server serves `/theme.css` (it serves `ui/` statically; confirm the build/packaging copies `ui/*.css`. `packaging/` and `LabImage.exe` bundle the ui folder, so grep `packaging/` for `report-ui.css` and add `theme.css` there the same way).
   *Verify:* the app loads, the Labeling look barely changes, the smoke test passes, and `window.labErrors` is empty.
2. **Remove the dark theme.** Delete the `report-ui.css` `<link>` in `editor.html`. Port its layout rules unscoped into `workspace.css` (3.2–3.7, 4.5 Tubes). Delete the file and its packaging entry.
   *Verify:* Report mode is light; rail, strip, inspector and Tubes table render at 1280; Tube single-pane works; `getComputedStyle(document.documentElement).colorScheme==='light'`.
3. **Tokenize `workspace.css`.** Replace every hex with a token, delete the base rules that theme.css now owns, and delete `.edit-tools`/`.tool-group` toolbar styling.
   *Verify:* `grep -oE "#[0-9a-fA-F]{3,8}\b" ui/workspace.css ui/labimage.css` returns nothing except documented data colors; both modes at 1280 match the shell in section 3.
4. **Reduce `labimage.css`** to 6.1's list plus the home layout (4.11).
   *Verify:* the home screen at 1280 and 760 widths, and the mode cards are keyboard-reachable.
5. **JS changes in `labimage.js`** (coordinate first):
   a. Move `nav.steps` into the header (3.1). Wrap step numbers in `b.step-n`. Set `data-short`.
   b. `labRailRender`/`labRailOrder`: icon rail in both modes.
   c. `#toolStrip`: drop `lab-report-only`; `labStrip()` runs in both modes and always sets `body.dataset.tool`.
   d. Remove Korean (5.9) and rewrite copy (5.1–5.6, 5.10). Mode badge and engine text.
   e. Tubes table: chips for T#/D#, header chips, footer copy, `aria-label` on `.none`.
   f. Add ICON keys (4.12); use them for `#openPoreDetails`, `#saveEditorImages`, collapsible chevrons and `#tubeCalib`.
   g. `drawManualMeasurement` reads `--measure`.
   h. The Tube segmented control (4.2), if the owner adds the measurement mode.
   *Verify:* the smoke test passes; the S/A/D canvas-top checks pass with the strip now visible in Labeling.
6. **Other JS and HTML copy:** editor.html (glyphs, Title Case, `?` typo, `Object Details ↗`), workspace.js (`Open analysis`, `Image and scale`, `Save PDF, HWPX and Word`, comma-joined details), report-composer.js (glyphs, `Add contents`, …), object-details.js, region-queue.js.
   *Verify:* `grep -nE "→|↗|↻|☰|＋| · " ui/*.js ui/*.html` returns only the intentional hits (none expected).
7. **QA pass** (6.3), then optional `/impeccable audit` and `polish` once the engine can be downloaded.

### 6.3 QA checklist

**Both modes, every screen:** Home; Load (New image, Open analysis with items, empty, error); Setup (uncalibrated, calibrated, Labeling processing); Editor in Select, Add, Point +, Point −, Box, Polygon, Delete, advanced Ellipse/Cut, and Report Tube (empty, tracing with 1 and 2+ points, results, selected row, fresh row, error "already measured", not calibrated); Region queue and preview with overlap; Object details dialog (table, histogram, scatter, column picker, target picker) and the separate details window; Report composer with all 6 dialogs; export success and failure.

**States:** hover, focus-visible, pressed, disabled (busy and no image), busy (> 300 ms shows the bar; a quick action shows none), error (status bar, inline, field).

**Widths:** 900 (one column, horizontal rail, no page-level horizontal scroll), 1280 (default; document bar on one line, strip on one line), 1600 (wide inspector). Also check 1100 for the mid band. At 900, confirm the stepper highlights the current step (an earlier capture showed "1 Load image" active while the editor was visible).

**Keyboard only:** Tab order header, then steps, then rail, then document bar, then strip, then canvas, then inspector, then status. Every control has a visible ring (canvas: two-tone ring). S/A/D/T shortcuts, Enter, Esc, Backspace and Ctrl+Z work in Tube. Arrow keys move inside `#tubeMeasure`. Table rows activate with Enter/Space. Dialogs trap focus (native `<dialog>`) and close with Esc. Collapsibles toggle with Enter/Space.

**Accessibility checks:** contrast with DevTools on `--text-3` over `--surface-sunken` (4.84) and on hints; icon-only buttons have names; `prefers-reduced-motion: reduce` emulated (no dialog slide, no fresh-row fade, static busy bar, no collapsible rotation).

**Text:** the Korean grep (5.9) prints nothing. `document.body.innerText` contains no Hangul in both modes. `document.documentElement.lang==='en'`.

**Console:** `window.labErrors` is empty after each flow. DevTools console has no CSS or 404 errors (`/theme.css` is served; `/report-ui.css` is no longer requested).

**`scripts/lab_ui_smoke.py` expectations that must stay true** (the design must not break them):
- `labHome` visible at start, with `.hidden` toggling (`labHome.classList.contains('hidden')`).
- `document.documentElement.lang==='en'`.
- In Report, `$('normalizeEnabled').closest('section')` and `$('preprocessingImage').closest('section')` compute to `display:none` (keep `.lab-label-only`).
- `[data-mode="polygon"]` is not `display:none` in Report.
- `[data-panel="analysis"]` is `display:none` in Labeling.
- `#updateRegionPreview` is not `.hidden` after a Point + correction.
- The canvas top moves less than 1 px between S, A and D in Labeling: the fixed 40 px strip row and the shared `#selectionActions` cell (3.2) are what guarantee this now that the strip shows in Labeling.
- No JS errors (`window.labErrors`).
- All ids called by the test exist: `runAnalysis`, `apply`, `manualStyle`, `manualStart`, `manualSave`, `manualAxis`, `manualAutomatic`, `updateRegionPreview`, `predict`, `target`, `status`, `composedReportPreview`, `analysisPanel`, `setupPanel`, `labCalibrated`, `labAutoCommit`.

**Proposed additions to the smoke test** (for its owner; not edited here):
- `check(!/[\uac00-\ud7a3]/.test(document.body.innerText),'Korean text in UI')` in both modes.
- `check(getComputedStyle(document.body).backgroundColor==='rgb(233, 235, 238)','Light theme missing')` in both modes.
- `check(document.querySelector('#tools [data-mode=select] svg'),'Icon rail missing')` in Labeling.
- `check(document.querySelector('header .steps'),'Stepper not in header')`.

---

## Implementation notes: skill lookups

Implemented 2026-11-09. `frontend-design:frontend-design` and `ui-ux-pro-max:ui-ux-pro-max` were loaded before coding and again for the final polish pass over the QA screenshots. Each lookup below was run with `scripts/search.py` from the ui-ux-pro-max skill.

| Lookup | Key recommendation | Where applied, or why rejected |
|---|---|---|
| `--design-system "scientific instrument measurement desktop tool precision" --density 9 --motion 2 --variance 3` | Minimalism and Swiss style; "Operation orange on dark"; Inter; scroll-reveal motion | Style adopted (section 1.4). Palette, Inter and scroll reveal rejected again for the same reasons as 1.4: dark mode is banned, orange fights the yellow overlay, the app is offline. |
| `"data-dense dashboard" --domain style` | 8 px gaps, 12 px padding, 12-14 px text, sticky table heads, row highlight on hover | `theme.css` table rules: 32 px rows, sticky `th` and `tfoot`, hover fill, 12-13 px cells. KPI cards rejected: the Tubes readout is the KPI. |
| `"swiss minimalism grid" --domain style` | No decoration, clear hierarchy, hover 200-250 ms | Hairline-only inspector, one radius per level. Hover kept at 90 ms (`--dur-1`) for the click loop. |
| `"tabular numbers data" --domain typography` | Mono for data, sans for labels (Fira pair) | Cascadia Mono only in values, IDs, zoom/opacity readouts; Segoe UI for labels. Removed mono from sentences (`#calibrationInfo`, `#poreSelectionInfo`) during polish. |
| `"scientific laboratory light neutral" --domain color` | Neutral gray plus one link blue | Kept the spec's cool gray and single indigo ink; the blue `#2563eb` plot bars in Object details now read `--chart-bar`. |
| `"data table sticky header dense" --domain ux` | Tables scroll inside a wrapper, never the page | `.results-wrap` scrolls; the readout was reworked (SD on its own line, wrapping headers) so it fits 304-384 px without horizontal scroll. |
| `"segmented control toggle group" --domain ux` | Set the final state directly; do not depend on transition end | Tube measure control rebuilt from native radios (`#tubeKind.segmented`): state is the checked radio, arrow keys are native, choice persists in localStorage. |
| `"toolbar icon button tooltip label" --domain ux` | Compact labels stay on one line; full text reachable without hover-only tooltips | Rail labels never wrap; at 1000-1279 they become visually hidden but stay in `aria-label`. Tool strip keys that do not fit drop whole (wrap to a clipped line) instead of being cut mid-word. |
| `"keyboard focus visible ring" --domain ux` | Visible ring on every control, including inside modals | One `--focus` ring; two-tone ring on the canvas; rail moved first in DOM so Tab follows rail, document bar, strip, canvas, inspector. |
| `"form label helper text error" --domain ux` | Errors announced; feedback after submit | `#status` stays `role=status`; errors keep the danger bar; `#tubeStatus` mirrors tube errors; library load failures get `.error`. |
| `"modal dialog focus trap escape" --domain ux` | Focus visible inside modal | Native `<dialog>`; icon close buttons with names; the non-modal Object details window got a z-index so sticky table heads cannot cover it. |
| `"empty state call to action" --domain ux` | Message plus action | Tubes empty state with `Start tracing`; library empty state with a `New image` button. |
| `"loading indicator delay" --domain ux` | (no direct match; returned tap delay) | Fallback to the spec: busy bar after `--busy-delay` 300 ms. |
| `"reduced motion animation" --domain ux` | Honor `prefers-reduced-motion`; animate 1-2 things | Durations go to 0; busy bar becomes static; fresh-row flash becomes a static tint. Only dialogs, busy bar and the fresh row animate. |
| `"touch target size minimum" --domain ux` | WCAG 2.5.8: 24 x 24 px on web | 28 px controls, 24 px small and icon buttons. |
| `"horizontal scroll responsive" --domain ux` | Content fits the viewport | Checked at 700, 900, 1100, 1280 and 1600: `scrollWidth === clientWidth`. |
| `"icon only button accessible label" --domain icons` | Decorative icons `aria-hidden`, icon buttons named | `ui/icons.js` emits `aria-hidden` SVG; every icon-only button keeps an `aria-label`. |
| `"tabs active state underline" --domain ux` | Highlight the current location | Underline tabs (Load, report editor, Object details); filled step number for the current step. |
| `"color not only indicator" --domain ux`, `"disabled state contrast" --domain ux` | Do not rely on color alone; disabled must look disabled | Done steps get a check icon, not only green; `button.danger:disabled` now uses `--text-disabled` (found in polish). |
| Polish: `"badge chip label wraps"`, `"loading feedback status"`, `"monospace numbers alignment"` | Chips stay on one line; feedback after every action | Measure chips are `nowrap`; footer `(n = 5)` uses no-break spaces; status verbs match actions ("Measured" for a width spot, "Traced" for a trace). |
| Tube drag gestures: `"dragging movements alternative" --domain ux` | WCAG 2.2 (2.5.7): every drag needs a single-pointer alternative | Left drag traces a tube and right drag boxes D, but clicking both ends stays, and **Width only keeps its one-click mode**: it is the single-pointer alternative to the right-drag box (and the only width gesture for pen or touch, which have no right button). |
| `"gesture discoverability hint" --domain ux` | (returned mobile gesture conflicts; no direct match) | Fallback: teach gestures in place. Idle strip steps read "Drag along the tube" and "Right-drag a box for width (optional)"; both labels stay visible from 1280 px (`.ts-steps.idle`), since they are alternatives, not a sequence. Once a click trace starts, the strip switches to the three click steps. Empty state and panel hint lead with drag, then right-drag, then "click both ends". |
| `"loading feedback status"` (reused) | Show loading, then success or error | The sent stroke or box stays on the image at 60 % opacity while the request runs (with the busy bar); errors go to `#status` and `#tubeStatus` as before. |
| `"drag threshold accidental"` | (no direct match) | Fallback: 5 screen px of travel separates a click from a drag, so click, Shift-click and Enter work unchanged. Stroke points are kept about every 4 screen px (at least 1 image px) and evenly decimated to at most 300. Esc, pointercancel, lost capture, window blur and switching tools cancel a drag. |
| frontend-design: live image marks | Data colors stay on the image | Stroke and box use `--trace` cyan on the existing dark halo, never the saved `--measure` yellow. The box is a dashed cyan outline with a 14 % cyan fill, so it reads as a selection, not a measurement. |
| Tube live preview: `"drag live preview feedback" --domain ux`, plus frontend-design | (no direct match; returned the drag single-pointer rule, already met) | Fallback from frontend-design: one main line. While dragging, the returned centerline takes the existing main stroke style (`--trace` cyan, 2.2 px on the 5 px dark halo); the hand stroke drops to 1.2 px at 50 % opacity underneath, so the user sees the app following the tube and the stroke past the last preview stays visible. No animation, no new text. After release the last preview stays at the 60 % sent opacity until the commit answers. |
| Particle tool (2026-11-11): `"mode switch segmented tool" --domain ux`, retry `"toggle group" --domain ux` | (no match on either) | Fallback to 4.2: the existing native-radio `.segmented` control, reused for `#particleMode` (Detect / Click / Line, kept in localStorage) and `#particleAxis` (Length / Width, Line only). |
| `"long running action progress" --domain ux` | Show progress for multi-step processes | Detect takes about 5 s: the busy bar plus a status that says so ("Detecting particles… (about 5 s)"); all particle controls are disabled while it runs. No step indicator: it is one step. |
| `"batch result summary feedback" --domain ux` | (returned error summaries; not a fit) | Fallback from `"loading feedback status"`: after Detect one status line says what was added and what was left out and why ("Added 12 particles. Left out 9: 4 overlapped, 3 cut off, 2 standing."), zero counts dropped, overlap kinds merged. |
| `"empty state call to action" --domain ux` | Message plus action | `#particleEmpty`: three short sentences, one per way, and a primary `Detect particles` button. |
| `"dragging movements" --domain ux` | WCAG 2.5.7: a single-pointer alternative for every drag | Line mode: press-drag-release draws a line, and two clicks draw the same line. Detect is a button. |
| frontend-design, Particle | Reuse; one bold element | No new colours or type. Live line is measurement yellow `#ffff00` on the existing dark halo with small end dots and no numbers (as the user asked for the Tube manual line); the sent line stays at 60 % until the server answers. |

frontend-design guidance applied beyond tokens: the home cards show a miniature of each workspace's output on the gray image well (yellow object outlines with IDs for Labeling, a traced tube with a `T1` chip for Report) instead of abstract line art; no eyebrows, arrows or middle-dot meta strings remain; copy is sentence case with verbs; one bold element (the yellow readout chips), everything else quiet.

Deviations from this spec, decided during implementation:
- The Tube measure control keeps its existing id `#tubeKind` (4.2 allows this) and its values `td`/`t`/`d`. It sits in the tool strip, right-aligned, Tube only. The kind hint stays in the Tubes panel.
- 4.2 "hide the column that is not measured" was not done: the table mixes rows from all three kinds, so both columns stay and unmeasured cells show `—`.
- Plot axis choices and report plot figures are English: `report_workspace.plot_choices` returns English labels, and `export_plot(..., report=True)` keeps the report figure style without Korean labels.
- The Tube kind and line help moved from the Tubes panel (`#tubeKindHint`, `#tubeHint`) into the `title` tooltips of `#tubeKind` and `#tubeLine` (2026-11-11, user feedback "far too much text on the right"). Trace progress shows in the strip; `#tubeStatus` in the inspector now shows errors only. Tube behaviour is unchanged.

## Particle workflow (Report, sample Particles; 2026-11-11)

Flow: Set up (calibration) -> automatic detection -> **Select particles** -> **Edit lines** -> Particle details / Save images -> Build report. It follows PoreSAM's review: automatic analysis first, raw image left and result right, click to select, Shift-click (or Ctrl-click) for more, Delete removes, the object list, the Details window, then the report.

| Stage | What the user sees | What the user does | Requests |
|---|---|---|---|
| Set up | Segmented `Sample`: Particles / Tubes (CNT), native radios, remembered in `localStorage['labimage.sample']`, default Particles. The primary button reads **Detect particles** (Tubes: Open measurement workspace). | Ticking **Confirm calibration** (a real click, `isTrusted`) starts the analysis and detection at once. A scale read from the microscope file is pre-confirmed without an event, so it waits for the button. | `analyze`, then `detect-particles {}` when the new workspace is empty |
| Select particles | Two panes: **Raw image** left, **Selected particles** right (outline, tint, IDs from the object layer; no lines). Strip: stages 1/2, Detect particles, Remove selected (n), Next: edit lines. | Click a particle = select (object-list.js `pickPoreAtPoint`, as in Select); Shift/Ctrl-click toggles; Delete/Backspace or the button removes all selected; Esc clears. A plain click where there is no object adds the particle there; with a selection it first clears it (PoreSAM). | `object-at-point {point}`; `delete {target_ids:[...]}` (one request, one undo); `measure-particle {point}` |
| Edit lines | One image. Every row's `length_line` / `width_line` drawn on the canvas: length orange `--particle-length` with bar ends, width sky blue `--particle-width` with round ends, both on a dark halo. Selected line: thicker with white end handles. Strip: Select / Draw, Length / Width (Draw only), Remove or Delete line, Build report. | Select: click within 6 screen px of a line selects it (else the particle under the click); Delete removes only that line. Draw: click both ends, or press-drag-release; Esc cancels the first point. With one particle selected the new line replaces that axis. | `particle-line {axis, points:[[x,y],[x,y]], object_id?}`; `particle-line {object_id, axis, points:null}` |
| Details | The list panel's button reads **Particle details** and opens the existing detached window, titled Particle Details: ID, Length, Width, Source; Histogram and Scatter offer Length and Width only; the plot line gives n, mean and SD. | Table, histogram, CSV and plot export as for objects. | `details-plot` (existing) |
| Save images | Document bar Save images (unchanged flow, name(2) lengths, name(3) widths, two CSVs, asks before replacing). Then a modal **Saved** dialog lists the folder and file names; OK closes, Esc closes. No Open folder: the backend has no reveal API. Same dialog for Tubes. | | `save-labels` |
| Build report | Header step 4, or the strip's Build report. Composer unchanged; for particle rows the plot dialog defaults to Length / Width. | | existing |

Rules kept: the strip is one 40 px row at 1000 px and wider (legends sr-only, `Remove selected` shortens to `Remove` below 1280, swatches hide below 1280), so the canvas never moves when a button appears. Saved figures stay yellow; the two line colours are on screen only. Colour is never the only cue (line ends differ, radio labels name the axis). Not done: dragging an end handle to move a line end (not needed for the asked flow; adds a third pointer mode).

Text reduction: the inspector shows the results table and one guidance line of at most 12 words (`#particleModeHint`). The long `#particleHint` and `#tubeHint` paragraphs are gone; empty states are icon, one sentence, one button; detection status is "Added 10. Left out 11." with the reasons in the status bar's tooltip.

### Skill lookups for this section

- **frontend-design** (loaded): kept the Bench instrument world; spent the one new visual idea on the two measurement-line colours with distinct end shapes. Rejected adding a new navigation; the stages reuse the strip's step list (`.ts-steps`, now buttons for the other stage).
- **ui-ux-pro-max**: `"color blind safe line pair" --domain ux` -> "Color Only: use icons/text in addition to color" (adopted: bar vs round ends, labelled radios). `"accessible colors line chart" --domain chart` -> "distinct colors + distinct line styles, never hue alone" (adopted; orange/sky blue, the deuteranopia-safe pair, equal lightness, so shape carries the difference in greyscale). `"modal dialog focus trap escape" --domain ux` -> visible focus inside modals (native `showModal`, OK focused, Esc closes). `"wizard step indicator progress" --domain ux` -> "Step 2 of 4 indicator" (the strip's numbered stages). `"split view compare before after" --domain ux` returned only a visionOS result: no verified match, so the two-pane layout follows the existing comparison panes. `"colorblind accessible data overlay" --domain color` returned product palettes (citizen science, analytics), rejected as off-topic.
- **impeccable**: the launcher could not download its engine offline, so `context` and `detect` did not run; reviewed by hand against audit.md. Findings fixed: an unused `--particle-halo` token removed; the strip overflowed at 1000 px (fixed, measured in a static harness at 1000 and 1280 px). Open: canvas selection is mouse-only (rows in the table are keyboard-selectable and Delete works from them); hidden Tube trace progress is no longer in the inspector's live region (the strip shows it).

Scope note (2026-11-11): this pass ships Sample, the calibration -> detection chain, Select particles and the text reduction. The next stage plugs in through `#particleNext` ("Next: edit lines"), which calls `window.particleEdit?.open()` when a separate module provides it, and falls back to the built-in Edit lines in `ui/labimage.js` (section "Particle tool", functions `particleLine`, `particleLineAt`, `particleDeleteSelected`, drawing in `particleStroke`). The strip's `#particleDetails` ("Details") opens the existing Details window. The Saved dialog (`labShowSaved`, `#labSavedDialog`) also lives in `ui/labimage.js`.
