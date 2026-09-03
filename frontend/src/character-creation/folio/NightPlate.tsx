/**
 * A night plate (#3540): the night is literal and appears at exactly two
 * moments, arrival and post-submission (design law §1). Constant night
 * literals in both themes; the realm's text ink comes from cg.css.
 */

import type { CSSProperties, ReactNode } from 'react';

interface NightPlateProps {
  eyebrow: string;
  title: string;
  /** `p` on a page that has its own h1 (arrival); `h2` after submission. */
  titleAs?: 'p' | 'h2';
  children?: ReactNode;
  door?: { label: string; onClick: () => void; disabled?: boolean };
  quiet?: { label: string; to?: string; onClick?: () => void };
  imprint?: boolean;
  /** Optional CMS art behind the night (the old `cg_stage` page background). */
  backgroundImage?: string;
  id?: string;
  titleId: string;
}

export function NightPlate({
  eyebrow,
  title,
  titleAs = 'p',
  children,
  door,
  quiet,
  imprint,
  backgroundImage,
  id,
  titleId,
}: NightPlateProps) {
  const Title = titleAs;
  const eyebrowId = `${titleId}-eyebrow`;
  const style: CSSProperties | undefined = backgroundImage
    ? {
        backgroundImage: `linear-gradient(rgba(14,17,22,0.72), rgba(14,17,22,0.72)), url(${backgroundImage})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }
    : undefined;
  return (
    <section
      className="plate-night"
      aria-labelledby={`${eyebrowId} ${titleId}`}
      id={id}
      style={style}
    >
      <div className="plate-inner">
        <span className="plate-no" id={eyebrowId}>
          {eyebrow}
        </span>
        <Title className="plate-title" id={titleId} tabIndex={titleAs === 'h2' ? -1 : undefined}>
          {title}
        </Title>
        {children}
        {(door || quiet) && (
          <div className="plate-door">
            {door && (
              <button type="button" className="btn" onClick={door.onClick} disabled={door.disabled}>
                {door.label}
              </button>
            )}
            {quiet && quiet.to && (
              <a className="btn-quiet" href={quiet.to}>
                {quiet.label}
              </a>
            )}
            {quiet && !quiet.to && (
              <button type="button" className="btn-quiet" onClick={quiet.onClick}>
                {quiet.label}
              </button>
            )}
          </div>
        )}
        {imprint && <p className="plate-imprint">As Arx endures, we remember</p>}
      </div>
    </section>
  );
}
