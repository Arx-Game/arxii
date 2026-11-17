/**
 * The aura in words and in colour (#5123).
 *
 * The magic app's standing rule is that player-facing data is narrative rather than
 * numerical, so this is the one place the figures of an aura turn into language. The
 * sheet's halo, the Settle your aura dialog and the character creation preview all read
 * their sentences and their colours from here.
 */

/** One affinity's share of an aura. `percent` is on any scale; only the proportions matter. */
export interface AuraShareInput {
  name: string;
  percent: number;
}

/** A CSS-safe class suffix for an affinity name ("Celestial" -> "celestial"). */
export function affinitySlug(name: string): string {
  return name.toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

/**
 * A share of a whole, in words. The thresholds are the backend's `share_in_words`
 * (`src/world/magic/services/drift.py`), so the aura reads the same on every surface.
 */
export function shareInWords(share: number, total: number): string {
  const part = total > 0 ? share / total : 0;
  if (part <= 0) return 'none';
  if (part < 0.08) return 'a trace';
  if (part < 0.18) return 'a tenth';
  if (part < 0.28) return 'a fifth';
  if (part < 0.4) return 'a third';
  if (part < 0.58) return 'half';
  if (part < 0.8) return 'most';
  return 'nearly all';
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** "most" reads "Mostly primal"; "a trace" reads "a trace of abyssal". */
function phrase(words: string, name: string, leading: boolean): string {
  if (words === 'most') return leading ? `mostly ${name}` : `most ${name}`;
  if (words === 'a trace') return `a trace of ${name}`;
  return `${words} ${name}`;
}

/**
 * The aura's split as one sentence, largest share first: "Mostly primal, a third
 * abyssal." Silent when the aura is unformed and every share is zero.
 */
export function auraSentence(shares: AuraShareInput[]): string {
  const held = shares
    .filter((row) => row.percent > 0)
    .map((row) => ({ name: row.name.toLowerCase(), percent: row.percent }))
    .sort((a, b) => b.percent - a.percent);
  if (held.length === 0) return '';
  const total = held.reduce((sum, row) => sum + row.percent, 0);
  if (held.length === 1) return `All of it ${held[0].name}.`;

  const parts = held.map((row, index) =>
    phrase(shareInWords(row.percent, total), row.name, index === 0)
  );
  return `${capitalise(parts.join(', '))}.`;
}

/** One coloured stretch of a halo, in the order drawn. */
export interface HaloSegment {
  /** The affinity's slug (`affinitySlug`). */
  slug: string;
  percent: number;
}

/**
 * A `conic-gradient` for the halo: one stretch per segment, sized by its share, each
 * opening on its own glow so the edges read as light rather than as a chart. The colours
 * are the `--aura-*` tokens in `character_sheets/sheet.css`.
 */
export function haloGradient(segments: HaloSegment[]): string {
  const held = segments.filter((segment) => segment.percent > 0);
  const total = held.reduce((sum, segment) => sum + segment.percent, 0);
  if (total <= 0) return 'none';
  let start = 0;
  const stops = held.map((segment) => {
    const end = start + (segment.percent / total) * 100;
    const colour = `var(--aura-${segment.slug}, var(--aura-other))`;
    const glow = `var(--aura-${segment.slug}-glow, var(--aura-other))`;
    const solid = Math.min(end, start + 3);
    const stop = `${glow} ${start.toFixed(2)}%, ${colour} ${solid.toFixed(2)}% ${end.toFixed(2)}%`;
    start = end;
    return stop;
  });
  return `conic-gradient(from -90deg, ${stops.join(', ')})`;
}
