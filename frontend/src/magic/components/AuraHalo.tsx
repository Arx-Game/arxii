/**
 * AuraHalo (#5123, Screen 3 of the approved demo): a character's aura as a halo, with
 * the split said in words beside it, never as numbers.
 *
 * The sheet draws it, the Settle your aura dialog draws a small one per exit, and the
 * character creation preview draws it too, so every input is optional beyond the shares:
 *
 * - `settled` draws who the character is as a dashed ring just outside the halo.
 * - `mire` draws what a Sineater took from the Mire apart from their own Abyssal, with a
 *   key naming the two.
 * - `unsettled` makes the halo restless and shows the Unsettled status in place of the
 *   split sentence.
 *
 * The halo's `children` sit under the words (the sheet's Settle your aura button).
 */

import { useId, type ReactNode } from 'react';
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
  /** Who the character is per affinity; draws the dashed ring when given. */
  settled?: AuraShareInput[];
  mire?: AuraHaloMire | null;
  unsettled?: boolean;
  /** The sentence naming what made them unsettled; shown in place of the split. */
  unsettledLine?: string;
  /** `mini` is the small halo beside a sentence, for a dialog exit. */
  size?: 'full' | 'mini';
  /** Overrides the sentence built from the shares. */
  sentence?: string;
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

interface RingProps {
  settled: AuraShareInput[];
}

/** The dashed ring: one arc per settled affinity, cut into dashes by a mask. */
function SettledRing({ settled }: RingProps) {
  const maskId = `aura-ring-${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const held = settled.filter((share) => share.percent > 0);
  const total = held.reduce((sum, share) => sum + share.percent, 0);
  if (total <= 0) return null;
  let start = 0;
  const arcs = held.map((share) => {
    const length = (share.percent / total) * 100;
    const slug = affinitySlug(share.name);
    const arc = (
      <circle
        key={slug}
        cx={50}
        cy={50}
        r={49}
        fill="none"
        pathLength={100}
        stroke={`var(--aura-${slug}, var(--aura-other))`}
        strokeWidth={1.6}
        strokeDasharray={`${length} ${100 - length}`}
        strokeDashoffset={-start}
      />
    );
    start += length;
    return arc;
  });
  return (
    <svg
      className="aura-halo-ring"
      viewBox="0 0 100 100"
      aria-hidden="true"
      data-testid="aura-halo-ring"
    >
      <mask id={maskId} maskUnits="userSpaceOnUse" x={-10} y={-10} width={120} height={120}>
        <circle
          cx={50}
          cy={50}
          r={49}
          fill="none"
          stroke="white"
          strokeWidth={4}
          pathLength={100}
          strokeDasharray="0.9 0.9"
        />
      </mask>
      <g transform="rotate(-90 50 50)" mask={`url(#${maskId})`}>
        {arcs}
      </g>
    </svg>
  );
}

export function AuraHalo({
  shares,
  settled,
  mire,
  unsettled = false,
  unsettledLine = '',
  size = 'full',
  sentence,
  children,
}: AuraHaloProps) {
  const { own, mirePercent } = splitMire(shares, mire);
  if (own.length === 0 && mirePercent <= 0) return null;

  const segments: HaloSegment[] = own.map((share) => ({
    slug: affinitySlug(share.name),
    percent: share.percent,
  }));
  if (mirePercent > 0) segments.push({ slug: MIRE_SLUG, percent: mirePercent });

  const mireLine =
    mire && mirePercent > 0 && mire.words !== 'none'
      ? `${capitalise(mire.words)} of what you have gained came from the Mire.`
      : '';
  const split = sentence ?? [auraSentence(own), mireLine].filter(Boolean).join(' ');
  const words = unsettled && unsettledLine ? unsettledLine : split;
  const mini = size === 'mini';

  return (
    <div
      className={mini ? 'aura-halo-wrap-mini' : 'aura-halo-wrap'}
      data-testid="aura-halo"
      data-affinities={segments.map((segment) => segment.slug).join(' ')}
    >
      <div
        className={[
          'aura-halo',
          mini ? 'aura-halo-mini' : '',
          unsettled ? 'aura-halo-unsettled' : '',
        ]
          .filter(Boolean)
          .join(' ')}
      >
        <div className="aura-halo-disc" style={{ background: haloGradient(segments) }} />
        {settled && !mini ? <SettledRing settled={settled} /> : null}
      </div>
      <div className="aura-halo-words">
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
        {mirePercent > 0 && !mini ? (
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
        ) : null}
        {children}
      </div>
    </div>
  );
}
