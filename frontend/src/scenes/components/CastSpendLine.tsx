/**
 * What a cast spent (#5018): "7 anima spent (3 to call up shadow)". Read from the cast
 * response's technique result.
 */
import type { CastResultPayload } from '../actionTypes';
import type { PowerLedger } from '@/magic/types';

/** The label the power ledger gives the term a kindled resonance adds to a cast (#5231). */
export const KINDLED_CAST_LINE = 'kindled cast power';

export function CastSpendLine({ result }: { result: CastResultPayload }) {
  const technique = result.technique_result;
  if (!technique) {
    return null;
  }
  const callUp = technique.substance_call_up;
  return (
    <p className="text-xs text-muted-foreground" data-testid="cast-spend-line">
      {technique.anima_spent} anima spent
      {callUp && callUp.anima > 0 && ` (${callUp.anima} to call up ${callUp.label})`}
    </p>
  );
}

/**
 * What an unsettled caster is told about her focus (#5123): the server's own sentences,
 * the ones telnet prints. Nothing for a settled caster.
 */
export function CastFocusLines({ result }: { result: CastResultPayload }) {
  const lines = result.technique_result?.focus_lines ?? [];
  if (lines.length === 0) {
    return null;
  }
  return (
    <div className="space-y-0.5 text-xs" data-testid="cast-focus-lines">
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

/**
 * What the caster's affinity check made the cast worth (#5308): the server's own sentence, the
 * one telnet prints. Nothing when every worth was 100 percent.
 */
export function CastWorthLine({ result }: { result: CastResultPayload }) {
  const line = result.technique_result?.worth_line ?? '';
  if (line === '') {
    return null;
  }
  return (
    <p className="text-xs" data-testid="cast-worth-line">
      {line}
    </p>
  );
}

/**
 * The sentence above the power ledger when a cast worked in a kindled resonance was made
 * stronger by it (#5231, Screen 4 of the demo). It reads the resonance's name from the option
 * the caster cast in, and shows only while the ledger carries the kindled cast power line, so
 * a kindled resonance that added nothing claims nothing.
 */
export function CastKindledLine({
  resonanceName,
  ledger,
}: {
  resonanceName: string | null;
  ledger: PowerLedger | null | undefined;
}) {
  const carriesLine = ledger?.entries.some(
    (entry) =>
      entry.stage === 'term' && entry.source_label === KINDLED_CAST_LINE && entry.amount > 0
  );
  if (!resonanceName || !carriesLine) {
    return null;
  }
  return (
    <p className="text-xs" data-testid="cast-kindled-line">
      Your kindled {resonanceName} strengthened the cast.
    </p>
  );
}
