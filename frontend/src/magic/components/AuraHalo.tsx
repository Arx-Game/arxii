/**
 * AuraHalo (#5123, Screen 3 of the approved demo): a character's aura as a halo, with
 * the split said in words beside it, never as numbers.
 *
 * The sheet draws it, the Settle your aura dialog draws a small one per exit, and the
 * character creation preview draws it too, so every input is optional beyond the shares:
 *
 * - `settled` draws who the character is as one thin neutral dashed ring just outside the
 *   halo (the ring is the line; the halo growing past it is what unsettled means).
 * - `mire` draws what a Sineater took from the Mire apart from their own Abyssal, with a
 *   key naming the two. The sentence reads every share against the whole the halo draws,
 *   Mire included, and says the Mire's share as its own sentence after the character's.
 * - `unsettled` makes the halo restless and shows the Unsettled status in place of the
 *   split sentence. `unsettledAffinity` (the affinity name the aura payload carries as
 *   `unsettled_affinity_name`) tints the ring in that affinity's glow while unsettled; a
 *   settled ring stays neutral.
 * - `label` is a small caps line above the sentence ("Your aura").
 *
 * The halo's `children` sit under the words (the sheet's Settle your aura button).
 */

import type { CSSProperties, ReactNode } from 'react';
import '@/character_sheets/sheet.css';
import {
  affinitySlug,
  auraSentence,
  haloGradient,
  type AuraShareInput,
  type HaloSegment,
} from '@/magic/aura';

const MIRE_SLUG = 'mire';
const ABYSSAL_SLUG = 'abyssal';

/** The Mire's share of what the character has gained. */
export interface AuraHaloMire {
  /** The share in words, as the API sends it ("a third"). */
  words: string;
  /** The same share as a part of the whole, 0 to 1; sizes the Mire's stretch of the halo. */
  part: number;
}

export interface AuraHaloProps {
  /** What the character holds per affinity. The Mire's part is inside the Abyssal share. */
  shares: AuraShareInput[];
  /** Draws the dashed ring that marks who the character is. */
  settled?: boolean;
  mire?: AuraHaloMire | null;
  unsettled?: boolean;
  /** The sentence naming what made them unsettled; shown in place of the split. */
  unsettledLine?: string;
  /** The affinity that is unsettling the character; tints the ring while `unsettled`. */
  unsettledAffinity?: string;
  /** `mini` is the small halo beside a sentence, for a dialog exit. */
  size?: 'full' | 'mini';
  /** Overrides the sentence built from the shares. */
  sentence?: string;
  /** A small caps line above the sentence. */
  label?: ReactNode;
  children?: ReactNode;
}

function capitalise(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** The shares with the Mire's part lifted out of the Abyssal into its own entry. */
function splitMire(shares: AuraShareInput[], mire: AuraHaloMire | null | undefined) {
  const held = shares.filter((share) => share.percent > 0);
  const total = held.reduce((sum, share) => sum + share.percent, 0);
  const mirePercent = mire && mire.part > 0 ? mire.part * total : 0;
  if (mirePercent <= 0) return { own: held, mirePercent: 0 };
  let remaining = mirePercent;
  const own = held.map((share) => {
    if (affinitySlug(share.name) !== ABYSSAL_SLUG) return share;
    const taken = Math.min(share.percent, remaining);
    remaining -= taken;
    return { ...share, percent: share.percent - taken };
  });
  return { own, mirePercent: mirePercent - remaining };
}

/** The own shares as halo segments, the Mire's stretch appended when it has one. */
function haloSegments(own: AuraShareInput[], mirePercent: number): HaloSegment[] {
  const segments: HaloSegment[] = own.map((share) => ({
    slug: affinitySlug(share.name),
    percent: share.percent,
  }));
  if (mirePercent > 0) segments.push({ slug: MIRE_SLUG, percent: mirePercent });
  return segments;
}

/** The sentence's two parts: the aura's own words, and the Mire's line when it is shown. */
function haloWords(args: {
  own: AuraShareInput[];
  mirePercent: number;
  mire: AuraHaloMire | null | undefined;
  sentence: string | undefined;
  unsettledLine: string | null;
}): { words: string; mireWords: string } {
  const { own, mirePercent, mire, sentence, unsettledLine } = args;
  if (unsettledLine !== null) return { words: unsettledLine, mireWords: '' };
  // Each share is read against the whole the halo draws, the Mire's stretch included.
  const ownTotal = own.reduce((sum, share) => sum + share.percent, 0);
  const words = sentence ?? auraSentence(own, ownTotal + mirePercent);
  if (sentence !== undefined || !mire || mirePercent <= 0 || mire.words === 'none') {
    return { words, mireWords: '' };
  }
  return {
    words,
    mireWords: `${capitalise(mire.words)} of what you have gained came from the Mire.`,
  };
}

/** The ring's border colour when the aura is unsettled toward a named affinity. */
function ringStyle(unsettled: boolean, unsettledAffinity: string): CSSProperties | undefined {
  if (!unsettled || !unsettledAffinity) return undefined;
  return {
    borderColor: `var(--aura-${affinitySlug(unsettledAffinity)}-glow, var(--aura-other))`,
  };
}

/** The key naming the halo's two swatches, shown once the Mire has a stretch of it. */
function MireKey() {
  return (
    <div className="aura-halo-key" data-testid="aura-halo-mire-key">
      <span>
        <i className="aura-halo-swatch-own" />
        your own
      </span>
      <span>
        <i className="aura-halo-swatch-mire" />
        from the Mire
      </span>
    </div>
  );
}

/** The halo's class list: the mini and unsettled modifiers join the base class. */
function haloClassName(mini: boolean, unsettled: boolean): string {
  return ['aura-halo', mini ? 'aura-halo-mini' : '', unsettled ? 'aura-halo-unsettled' : '']
    .filter(Boolean)
    .join(' ');
}

interface HaloSentenceProps {
  words: string;
  mireWords: string;
}

/** The sentence under the halo: the aura's words, then the Mire's line when there is one. */
function HaloSentence({ words, mireWords }: HaloSentenceProps) {
  if (!words && !mireWords) return null;
  return (
    <p className="aura-halo-sentence" data-testid="aura-halo-sentence">
      {words}
      {mireWords ? (
        <>
          {words ? ' ' : ''}
          <span data-testid="aura-halo-mire-line">{mireWords}</span>
        </>
      ) : null}
    </p>
  );
}

export function AuraHalo({
  shares,
  settled,
  mire,
  unsettled = false,
  unsettledLine = '',
  unsettledAffinity = '',
  size = 'full',
  sentence,
  label,
  children,
}: AuraHaloProps) {
  const { own, mirePercent } = splitMire(shares, mire);
  if (own.length === 0 && mirePercent <= 0) return null;

  const segments = haloSegments(own, mirePercent);
  const { words, mireWords } = haloWords({
    own,
    mirePercent,
    mire,
    sentence,
    unsettledLine: unsettled && unsettledLine !== '' ? unsettledLine : null,
  });
  const mini = size === 'mini';

  return (
    <div
      className={mini ? 'aura-halo-wrap-mini' : 'aura-halo-wrap'}
      data-testid="aura-halo"
      data-affinities={segments.map((segment) => segment.slug).join(' ')}
    >
      <div className={haloClassName(mini, unsettled)}>
        <div className="aura-halo-disc" style={{ background: haloGradient(segments) }} />
        {settled && !mini ? (
          <span
            className="aura-halo-ring"
            aria-hidden="true"
            data-testid="aura-halo-ring"
            style={ringStyle(unsettled, unsettledAffinity)}
          />
        ) : null}
      </div>
      <div className="aura-halo-words">
        {label}
        <HaloSentence words={words} mireWords={mireWords} />
        {unsettled && !mini ? (
          <span className="aura-halo-status" data-testid="aura-halo-status">
            Unsettled
          </span>
        ) : null}
        {mirePercent > 0 && !mini ? <MireKey /> : null}
        {children}
      </div>
    </div>
  );
}
