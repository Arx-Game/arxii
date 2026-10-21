/** The instruments (#3540): mechanical inputs in a framed region, deliberately sans, purse at the head. */
import type { ReactNode } from 'react';

interface InstrumentFrameProps {
  label: string;
  ledger?: { left: ReactNode; right: ReactNode; over?: boolean };
  children: ReactNode;
}

export function InstrumentFrame({ label, ledger, children }: InstrumentFrameProps) {
  return (
    <div className="instruments">
      <span className="plate-label" aria-hidden="true">
        {label}
      </span>
      {ledger && (
        <div className="instr-ledger head">
          <span>{ledger.left}</span>
          <span className={ledger.over ? 'over' : undefined}>{ledger.right}</span>
        </div>
      )}
      {children}
    </div>
  );
}

export function InstrumentGroup({
  title,
  gloss,
  children,
}: {
  title: string;
  gloss?: string;
  children: ReactNode;
}) {
  return (
    <div className="instr-group">
      <div className="instr-group-h">
        {title} {gloss && <span>{gloss}</span>}
      </div>
      {children}
    </div>
  );
}

interface StatRowBaseProps {
  id: string;
  name: string;
  sub?: string;
  value: number;
  /** Bonus shown beside the value as "+1"; never folded into the number. */
  bonus?: number;
  max: number;
  /** When set, the name is a button that opens the gloss in the margin. */
  onWhy?: () => void;
  whyOpen?: boolean;
  /** Inline gloss under the row (narrow layouts). */
  gloss?: string;
  spec?: boolean;
  step?: number;
}

/** An adjustable row has steppers; a read-only row (a value granted, not bought) has none. */
type StatRowProps = StatRowBaseProps &
  (
    | {
        readOnly?: false;
        onChange: (value: number) => void;
        canDecrease: boolean;
        canIncrease: boolean;
        decreaseTitle?: string;
        increaseTitle?: string;
      }
    | { readOnly: true }
  );

export function StatRow(props: StatRowProps) {
  const { id, name, sub, value, bonus, max, onWhy, whyOpen, gloss, spec, step = 1 } = props;
  const pipCount = Math.max(0, Math.min(max, Math.round(value / step)));
  const pipMax = Math.round(max / step);
  return (
    <div className={spec ? 'stat-row spec' : 'stat-row'}>
      <span className="stat-name" id={id}>
        {onWhy ? (
          <button
            type="button"
            className="stat-why"
            aria-expanded={whyOpen ? 'true' : 'false'}
            aria-controls="why-note"
            onClick={onWhy}
          >
            {name}
          </button>
        ) : (
          name
        )}
        {sub && <small>{sub}</small>}
      </span>
      <span className={props.readOnly ? 'stat-pips granted' : 'stat-pips'} aria-hidden="true">
        {Array.from({ length: pipMax }, (_, i) => (
          <i key={i} className={i < pipCount ? 'on' : undefined} />
        ))}
      </span>
      <output className="stat-val" aria-labelledby={id}>
        {value}
        {bonus ? <small>{bonus > 0 ? `+${bonus}` : bonus}</small> : null}
      </output>
      {props.readOnly ? (
        // Keeps the fourth grid cell so a read-only row lines up with the steppered ones.
        <span />
      ) : (
        <span className="stat-step">
          <button
            type="button"
            disabled={!props.canDecrease}
            title={props.decreaseTitle}
            aria-label={`Lower ${name}`}
            onClick={() => props.onChange(value - step)}
          >
            −
          </button>
          <button
            type="button"
            disabled={!props.canIncrease}
            title={props.increaseTitle}
            aria-label={`Raise ${name}`}
            onClick={() => props.onChange(value + step)}
          >
            +
          </button>
        </span>
      )}
      {gloss && <p className="stat-gloss">{gloss}</p>}
    </div>
  );
}
