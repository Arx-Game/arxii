/**
 * What a cast spent (#5018): "7 anima spent (3 to call up shadow) · 1 Umbral resonance
 * spent". Read from the cast response's technique result.
 */
import type { CastResultPayload } from '../actionTypes';

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
      {callUp &&
        callUp.resonance > 0 &&
        ` · ${callUp.resonance} ${callUp.resonance_name} resonance spent`}
      {callUp?.blocked === 'too_little_resonance' &&
        ` · no resonance left to call up ${callUp.label}`}
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
