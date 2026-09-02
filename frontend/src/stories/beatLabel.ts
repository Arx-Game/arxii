/**
 * What a beat is called in player-facing lists: its authored hint, a neutral
 * placeholder when it is secret, or a bare label.
 */
export function beatLabel(beat: { player_hint?: string | null; visibility?: string }): string {
  if (beat.player_hint && beat.player_hint.trim()) return beat.player_hint;
  if (beat.visibility === 'secret') return '(Hidden Beat)';
  return 'Beat';
}
