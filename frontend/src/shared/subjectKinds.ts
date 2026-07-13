/**
 * Shared label map for StakeSubjectKind / TreasuredSubjectKind values.
 *
 * Both `boundaries` and `stories` use the same SubjectKind enum values
 * (they mirror each other per ADR-0010). This shared module avoids
 * duplicating the label map across both apps.
 */

export const SUBJECT_KIND_LABELS: Record<string, string> = {
  personal_jeopardy: 'Personal jeopardy',
  npc_fate: 'NPC fate',
  location: 'Location',
  faction: 'Faction relationship',
  item: 'Item',
  campaign_track: 'Campaign track',
  asset: 'Asset',
  custom: 'Custom',
};
