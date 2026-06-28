import { Badge } from '@/components/ui/badge';
import type { CreationProvenance } from '../types';

interface CreationProvenanceBadgeProps {
  provenance: CreationProvenance;
  /** Human label from the API (e.g. "Staff-created"). */
  display: string;
  /** Set for GM_TABLE: the table the character was authored for. */
  tableName: string | null;
}

/**
 * A viewable quality/trust signal on a roster character (#1506): staff-vetted vs a
 * player-GM's table creation. The GM variant names the table the GM vouches for it for;
 * it is informational only and never gates who may apply.
 */
export function CreationProvenanceBadge({
  provenance,
  display,
  tableName,
}: CreationProvenanceBadgeProps) {
  if (provenance === 'gm_table') {
    return (
      <Badge variant="secondary" title="Created by a player GM for their table — not staff-vetted">
        {tableName ? `GM-made · ${tableName}` : 'GM-made'}
      </Badge>
    );
  }
  if (provenance === 'staff') {
    return (
      <Badge variant="outline" title="Staff-created — held to the global content standard">
        Staff-created
      </Badge>
    );
  }
  return (
    <Badge variant="outline" title="Player-created original character">
      {display}
    </Badge>
  );
}
