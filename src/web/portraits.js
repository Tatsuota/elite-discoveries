/* ===========================================================================
   Codex-style body portraits — holographic wireframe renders in the style of
   the in-game ED Codex: thin luminous line art, scanline sphere, class-tinted.
   No external images: license-safe, offline, deterministic per body.
   window.PORTRAITS.body(bodyObj)  ->  SVG markup string (viewBox 0 0 100 100)
   =========================================================================== */
(function () {
  function hash(str) {
    let h = 1779033703 ^ str.length;
    for (let i = 0; i < str.length; i++) {
      h = Math.imul(h ^ str.charCodeAt(i), 3432918353);
      h = (h << 13) | (h >>> 19);
    }
    return h >>> 0;
  }
  function rng(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function category(cls) {
    if (!cls) return "rock";
    const c = cls.toLowerCase();
    if (c.includes("gas giant")) return "gas";
    if (c.includes("earthlike") || c.includes("water world")) return "life";
    if (c.includes("ammonia")) return "life";
    if (c.includes("icy") || c.includes("ice")) return "ice";
    return "rock";
  }

  // Wireframe globe: outline + meridians + parallels, clipped to the disc.
  function globe(id, stroke, R) {
    return `
      <g stroke="${stroke}" fill="none" stroke-width="0.7" opacity="0.75" clip-path="url(#${id}c)">
        <ellipse cx="50" cy="50" rx="${R * 0.55}" ry="${R}"/>
        <ellipse cx="50" cy="50" rx="${R * 0.22}" ry="${R}"/>
        <line x1="50" y1="${50 - R}" x2="50" y2="${50 + R}"/>
        <ellipse cx="50" cy="50" rx="${R}" ry="${R * 0.5}"/>
        <ellipse cx="50" cy="50" rx="${R * 0.87}" ry="${R * 0.25}" transform="translate(0 ${-R * 0.55})"/>
        <ellipse cx="50" cy="50" rx="${R * 0.87}" ry="${R * 0.25}" transform="translate(0 ${R * 0.55})"/>
      </g>`;
  }

  function planet(body) {
    const pal = body.palette || { base: "#6e655c", accent: "#af84cf" };
    const tint = pal.accent;             // class colour keeps bodies tellable-apart
    const cat = category(body.planetClass);
    const seed = hash((body.name || "") + (body.bodyId || ""));
    const rnd = rng(seed);
    const id = "p" + (seed % 999999);
    const R = 36;

    let detail = "";
    if (cat === "gas") {
      // Codex-style banding lines
      for (let i = 0; i < 5; i++) {
        const y = 50 - R + ((i + 1) / 6) * R * 2 + (rnd() - 0.5) * 4;
        detail += `<line x1="14" y1="${y}" x2="86" y2="${y}" stroke="${tint}"
          stroke-width="${0.6 + rnd() * 0.8}" opacity="${0.3 + rnd() * 0.35}" clip-path="url(#${id}c)"/>`;
      }
    } else if (cat === "life") {
      // faint landmass traces
      for (let i = 0; i < 4; i++) {
        const cx = 30 + rnd() * 40, cy = 30 + rnd() * 40, r = 5 + rnd() * 9;
        detail += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${tint}"
          stroke-width="0.6" opacity="${0.35 + rnd() * 0.25}" stroke-dasharray="2 2" clip-path="url(#${id}c)"/>`;
      }
      detail += globe(id, tint, R);
    } else {
      // rock / ice: crater marks over the wireframe
      detail += globe(id, tint, R);
      for (let i = 0; i < 5; i++) {
        const cx = 26 + rnd() * 48, cy = 26 + rnd() * 48, r = 1.5 + rnd() * 4;
        detail += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${tint}"
          stroke-width="0.6" opacity="${0.4 + rnd() * 0.3}" clip-path="url(#${id}c)"/>`;
      }
    }
    if (cat === "gas") detail += globe(id, tint, R);

    // holographic ring (planetary rings)
    let ringArt = "";
    if (body.rings && body.rings.length) {
      ringArt = `
        <ellipse cx="50" cy="50" rx="47" ry="12" fill="none" stroke="${tint}"
          stroke-width="0.9" opacity="0.65" transform="rotate(-16 50 50)"/>
        <ellipse cx="50" cy="50" rx="42" ry="10" fill="none" stroke="${tint}"
          stroke-width="0.5" opacity="0.35" transform="rotate(-16 50 50)"/>`;
    }

    return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <clipPath id="${id}c"><circle cx="50" cy="50" r="${R}"/></clipPath>
        <linearGradient id="${id}s" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${tint}" stop-opacity="0.14"/>
          <stop offset="100%" stop-color="${tint}" stop-opacity="0.03"/>
        </linearGradient>
      </defs>
      <circle cx="50" cy="50" r="${R + 7}" fill="none" stroke="${tint}" stroke-width="0.5"
        opacity="0.25" stroke-dasharray="1 5"/>
      <circle cx="50" cy="50" r="${R}" fill="url(#${id}s)"/>
      ${detail}
      <circle cx="50" cy="50" r="${R}" fill="none" stroke="${tint}" stroke-width="1.3" opacity="0.9"/>
      ${ringArt}
    </svg>`;
  }

  function star(body) {
    const col = body.color || "#ffcc6f";
    const seed = hash(body.name || "star");
    const rnd = rng(seed);
    const id = "s" + (seed % 999999);
    const compact = /^(D|N|H)/.test(body.starType || "") || body.starType === "SupermassiveBlackHole";
    const R = compact ? 16 : 26;
    let ticks = "";
    for (let i = 0; i < 16; i++) {
      const a = (i / 16) * Math.PI * 2;
      const r1 = R + 5, r2 = R + 9 + rnd() * 6;
      ticks += `<line x1="${50 + Math.cos(a) * r1}" y1="${50 + Math.sin(a) * r1}"
        x2="${50 + Math.cos(a) * r2}" y2="${50 + Math.sin(a) * r2}"
        stroke="${col}" stroke-width="0.8" opacity="${0.3 + rnd() * 0.4}"/>`;
    }
    return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
      <defs>
        <radialGradient id="${id}g" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stop-color="${col}" stop-opacity="0.5"/>
          <stop offset="70%" stop-color="${col}" stop-opacity="0.12"/>
          <stop offset="100%" stop-color="${col}" stop-opacity="0"/>
        </radialGradient>
      </defs>
      <circle cx="50" cy="50" r="${R + 16}" fill="url(#${id}g)"/>
      <circle cx="50" cy="50" r="${R + 7}" fill="none" stroke="${col}" stroke-width="0.5"
        opacity="0.3" stroke-dasharray="1 5"/>
      ${ticks}
      <circle cx="50" cy="50" r="${R}" fill="none" stroke="${col}" stroke-width="1.4" opacity="0.95"/>
      <circle cx="50" cy="50" r="${R * 0.6}" fill="none" stroke="${col}" stroke-width="0.6" opacity="0.5"/>
      ${compact ? `<circle cx="50" cy="50" r="${R * 0.3}" fill="${col}" opacity="0.9"/>` : ""}
    </svg>`;
  }

  window.PORTRAITS = {
    body(b) {
      if (b.type === "star") return star(b);
      if (b.type === "planet") return planet(b);
      // belt cluster: sparse asteroid arc, same holo style
      return `<svg viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <ellipse cx="50" cy="50" rx="38" ry="11" fill="none" stroke="#af84cf" stroke-width="0.8"
          opacity="0.5" stroke-dasharray="3 4"/>
        <circle cx="34" cy="46" r="2.4" fill="none" stroke="#af84cf" stroke-width="0.9" opacity="0.8"/>
        <circle cx="56" cy="55" r="1.7" fill="none" stroke="#af84cf" stroke-width="0.9" opacity="0.7"/>
        <circle cx="70" cy="48" r="2" fill="none" stroke="#af84cf" stroke-width="0.9" opacity="0.75"/>
      </svg>`;
    },
  };
})();
