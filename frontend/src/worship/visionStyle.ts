/**
 * The one treatment reserved for visions (#3779), used nowhere else: the feed line at the
 * delivery moment and the sheet's persistent card share it, the way Arx 1's green did on
 * telnet (where `|G[VISION]|n` still is). Emerald is otherwise unused in the palette.
 */
export const VISION_GLYPH = '✧';

export const VISION_FRAME_CLASS =
  'rounded-sm border-l-2 border-emerald-500 bg-emerald-500/5 ring-1 ring-emerald-500/20 dark:bg-emerald-400/5 dark:ring-emerald-400/20';

export const VISION_TEXT_CLASS = 'font-serif text-[0.95rem] leading-relaxed text-foreground';
