/* Elite-styled line icons. All use currentColor so CSS controls colour.
   Exposed as window.ICONS (name -> SVG markup string).                      */
window.ICONS = {
  diamond: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6">
    <path d="M12 2 L21 12 L12 22 L3 12 Z"/><path d="M12 6 L17 12 L12 18 L7 12 Z" stroke-width="1"/></svg>`,

  // first-discovery marker (filled diamond, the in-game tag look)
  tag: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M12 2 L21.5 12 L12 22 L2.5 12 Z"/></svg>`,

  star: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="12" cy="12" r="6" fill="currentColor" stroke="none"/>
    <g stroke-linecap="round"><path d="M12 1v3"/><path d="M12 20v3"/><path d="M1 12h3"/><path d="M20 12h3"/>
    <path d="M4 4l2 2"/><path d="M18 18l2 2"/><path d="M20 4l-2 2"/><path d="M6 18l-2 2"/></g></svg>`,

  probe: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.2" fill="currentColor" stroke="none"/>
    <path d="M12 3v3M12 18v3M3 12h3M18 12h3"/></svg>`,

  footfall: `<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8.5 3c1.6 0 2.4 1.7 2.4 3.8 0 2.6-1 4.4-2.6 4.4S5.9 9.4 5.9 6.9 6.9 3 8.5 3Z"/>
    <path d="M7 13.5c2 0 3.2 1 3.2 2.8 0 2-1 4.7-3 4.7s-2.8-2-2.8-3.9c0-2 .9-3.6 2.6-3.6Z"/>
    <circle cx="15.5" cy="5.5" r="1.5"/><circle cx="17.8" cy="7.4" r="1.2"/><circle cx="18.6" cy="10" r="1.1"/></svg>`,

  terraform: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 21c5-2 7-6 7-11V5l-7-2-7 2v5c0 5 2 9 7 11Z"/><path d="M9 11l2 2 4-4.5"/></svg>`,

  bio: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M12 3c0 5-7 5-7 10a7 7 0 0 0 14 0c0-5-7-5-7-10Z"/><path d="M12 21V9"/><path d="M12 13l3-2M12 16l-3-2"/></svg>`,

  geo: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round">
    <path d="M3 20h18L15 8l-3 5-2-3-7 10Z"/><path d="M13 4l2-2 2 2-2 2z" fill="currentColor"/></svg>`,

  lander: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <path d="M8 9h8l2 5H6l2-5Z"/><path d="M9 9V6h6v3"/><path d="M6 14l-2 5M18 14l2 5M9 14v4M15 14v4"/></svg>`,

  ring: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="12" cy="12" r="5"/><ellipse cx="12" cy="12" rx="10.5" ry="3.6" transform="rotate(-20 12 12)"/></svg>`,

  credits: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
    <circle cx="12" cy="12" r="9"/><path d="M15 9.5a3.5 3.5 0 1 0 0 5" stroke-linecap="round"/></svg>`,

  system: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.4">
    <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none"/>
    <ellipse cx="12" cy="12" rx="9" ry="4"/><ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(60 12 12)"/>
    <ellipse cx="12" cy="12" rx="9" ry="4" transform="rotate(120 12 12)"/></svg>`,

  lock: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
    <rect x="4.5" y="10.5" width="15" height="10" rx="1.5"/>
    <path d="M8 10.5V7a4 4 0 0 1 8 0v3.5"/>
    <circle cx="12" cy="15.2" r="1.4" fill="currentColor" stroke="none"/><path d="M12 16.4v2"/></svg>`,

  copy: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
    <rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`,

  check: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <path d="M5 12.5l4.5 4.5L19 6.5"/></svg>`,
};
