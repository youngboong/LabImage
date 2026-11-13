// One inline-SVG icon set: 24-unit viewBox, stroke currentColor, width 1.75, round caps (docs/ui-design.md 4.12).
window.LAB_ICON={
  select:'<path d="M6 4l11 7.5-5 1.2-2.4 5z"/>',
  particle:'<path d="M4 13.5L8.5 5l8.5-.5 3.5 7.5-5.5 7.5-8.5-.5z"/><path d="M6.5 16.5l11-9M9.5 9l4.5 5.5"/>',
  positive:'<circle cx="12" cy="12" r="8" stroke-dasharray="3 2.6"/><path d="M12 8.5v7M8.5 12h7"/>',
  'prompt-positive':'<circle cx="10" cy="14.5" r="3.2"/><path d="M18 3.5v6M15 6.5h6"/>',
  negative:'<circle cx="10" cy="14.5" r="3.2"/><path d="M15 6.5h6"/>',
  box:'<rect x="4" y="5" width="16" height="14" rx="1.5" stroke-dasharray="3.2 2.6"/>',
  polygon:'<path d="M5 18L7 7l9-3 4 9-8 6z"/>',
  ellipse:'<ellipse cx="12" cy="12" rx="9" ry="6" stroke-dasharray="3.2 2.6"/>',
  cut:'<path d="M4 20L20 4M4 4l5 5M20 20l-5-5"/>',
  delete:'<path d="M5 7h14M10 7V5h4v2M7 7l1 12h8l1-12M10.5 11v5M13.5 11v5"/>',
  back:'<path d="M9 5L4 10l5 5M4 10h9a5.5 5.5 0 010 11h-3"/>',
  clear:'<circle cx="12" cy="12" r="8"/><path d="M9 9l6 6M15 9l-6 6"/>',
  close:'<path d="M6 6l12 12M18 6L6 18"/>',
  external:'<path d="M14 4h6v6M20 4l-8.5 8.5M18 14v4.5A1.5 1.5 0 0116.5 20h-11A1.5 1.5 0 014 18.5v-11A1.5 1.5 0 015.5 6H10"/>',
  refresh:'<path d="M20 7v5h-5M4 17v-5h5M6.1 6.1A8 8 0 0 1 19.8 11M4.2 13a8 8 0 0 0 13.7 4.9"/>',
  grip:'<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
  plus:'<path d="M12 5v14M5 12h14"/>',
  upload:'<path d="M4 15v3.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V15M12 15V4M7.5 8.5L12 4l4.5 4.5"/>',
  save:'<path d="M4 15v3.5A1.5 1.5 0 005.5 20h13a1.5 1.5 0 001.5-1.5V15M12 4v11M7.5 10.5L12 15l4.5-4.5"/>',
  chevron:'<path d="M6 9l6 6 6-6"/>',
  'chevron-left':'<path d="M15 6l-6 6 6 6"/>',
  'chevron-right':'<path d="M9 6l6 6-6 6"/>',
  'chevron-up':'<path d="M6 15l6-6 6 6"/>',
  sort:'<path d="M8 10l4-4 4 4M8 14l4 4 4-4"/>',
  warning:'<path d="M12 4L2.8 19.5h18.4z"/><path d="M12 10v4.5M12 17.2v.1"/>',
  check:'<path d="M5 12.5l4.5 4.5L19 7.5"/>',
  columns:'<rect x="4" y="5" width="16" height="14" rx="1.5"/><path d="M9.5 5v14M14.5 5v14"/>'
};
window.labIcon=(name,cls='')=>`<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${window.LAB_ICON[name]||''}</svg>`;
// Replace a button's content with an icon and visible text (text '' gives an icon-only button that keeps its aria-label).
window.labIconButton=(button,name,text)=>{button.innerHTML=window.labIcon(name);if(text)button.append(text);return button};
