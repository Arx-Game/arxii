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
