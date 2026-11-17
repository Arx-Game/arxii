/**
 * AuraHalo (#5123, Screen 3 of the approved demo): a character's aura as a halo, with
 * the split said in words beside it, never as numbers.
 *
 * The sheet draws it, the Settle your aura dialog draws a small one per exit, and the
 * character creation preview draws it too, so every input is optional beyond the shares:
 *
 * - `settled` draws who the character is as one thin neutral dashed ring just outside the
 *   halo (the ring is the line; the halo growing past it is what unsettled means).
 * - `unsettled` makes the halo restless and shows the Unsettled status in place of the
 *   split sentence. `unsettledAffinity` (the affinity name the aura payload carries as
 *   `unsettled_affinity_name`) tints the ring in that affinity's glow while unsettled; a
 *   settled ring stays neutral.
 * - `label` is a small caps line above the sentence ("Your aura").
 *
 * The halo's `children` sit under the words.
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

export interface AuraHaloProps {
  /** What the character holds per affinity. */
  shares: AuraShareInput[];
  /** Draws the dashed ring that marks who the character is. */
  settled?: boolean;
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

/** The shares as halo segments, in the order drawn. */
function haloSegments(shares: AuraShareInput[]): HaloSegment[] {
  return shares
    .filter((share) => share.percent > 0)
    .map((share) => ({ slug: affinitySlug(share.name), percent: share.percent }));
}

/** The ring's border colour when the aura is unsettled toward a named affinity. */
function ringStyle(unsettled: boolean, unsettledAffinity: string): CSSProperties | undefined {
  if (!unsettled || !unsettledAffinity) return undefined;
  return {
    borderColor: `var(--aura-${affinitySlug(unsettledAffinity)}-glow, var(--aura-other))`,
  };
}

/** The halo's class list: the mini and unsettled modifiers join the base class. */
function haloClassName(mini: boolean, unsettled: boolean): string {
  return ['aura-halo', mini ? 'aura-halo-mini' : '', unsettled ? 'aura-halo-unsettled' : '']
    .filter(Boolean)
    .join(' ');
}

export function AuraHalo({
  shares,
  settled,
  unsettled = false,
  unsettledLine = '',
  unsettledAffinity = '',
  size = 'full',
  sentence,
  label,
  children,
}: AuraHaloProps) {
  const segments = haloSegments(shares);
  if (segments.length === 0) return null;

  const words =
    unsettled && unsettledLine !== '' ? unsettledLine : (sentence ?? auraSentence(shares));
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
        {words ? (
          <p className="aura-halo-sentence" data-testid="aura-halo-sentence">
            {words}
          </p>
        ) : null}
        {unsettled && !mini ? (
          <span className="aura-halo-status" data-testid="aura-halo-status">
            Unsettled
          </span>
        ) : null}
        {children}
      </div>
    </div>
  );
}
