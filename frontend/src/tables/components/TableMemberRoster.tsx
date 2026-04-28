/**
 * TableMemberRoster — member list in the TableDetailPage Members tab.
 *
 * GM sees all active members with a "Remove" CTA.
 * Non-GM viewers see all members (simplified view, no admin actions).
 *
 * TODO: For non-GM players, filter to only members who share a story with
 * the viewer. This requires cross-referencing StoryParticipation — deferred
 * until a backend endpoint or client-side intersection is implemented.
 * Currently shows all members for simplicity.
 */

import { Skeleton } from '@/components/ui/skeleton';
import { useTableMembers } from '../queries';
import type { GMTable } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TableMemberRosterProps {
  table: GMTable;
  onRemove?: (membershipId: number, personaName: string) => void;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function MemberRowSkeleton() {
  return (
    <div className="flex items-center justify-between py-2">
      <Skeleton className="h-4 w-40" />
      <Skeleton className="h-8 w-16" />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TableMemberRoster({ table, onRemove }: TableMemberRosterProps) {
  const isGM = table.viewer_role === 'gm' || table.viewer_role === 'staff';
  const { data, isLoading } = useTableMembers(table.id, { active: true });

  if (isLoading) {
    return (
      <div className="space-y-1">
        {[0, 1, 2].map((i) => (
          <MemberRowSkeleton key={i} />
        ))}
      </div>
    );
  }

  const members = data?.results ?? [];

  if (members.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground">No active members at this table.</p>
    );
  }

  return (
    <div className="divide-y">
      {members.map((membership) => (
        <div key={membership.id} className="flex items-center justify-between py-3">
          <div>
            <span className="font-medium">{membership.persona_name}</span>
            <span className="ml-2 text-xs text-muted-foreground">
              Joined {new Date(membership.joined_at).toLocaleDateString()}
            </span>
          </div>
          {isGM && onRemove && (
            <button
              type="button"
              className="rounded border border-destructive/30 px-2 py-1 text-xs text-destructive hover:bg-destructive/10"
              onClick={() => onRemove(membership.id, membership.persona_name)}
            >
              Remove
            </button>
          )}
        </div>
      ))}
    </div>
  );
}
