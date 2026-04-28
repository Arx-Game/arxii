/**
 * TableCard — single table row in the Tables list.
 *
 * Shows name, GM username, member_count, story_count, viewer_role badge, and a "View" CTA.
 */

import { useNavigate } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { GMTable, GMTableViewerRole } from '../types';

// ---------------------------------------------------------------------------
// Role badge
// ---------------------------------------------------------------------------

const ROLE_BADGE_VARIANTS: Record<GMTableViewerRole, { label: string; className: string }> = {
  gm: { label: 'GM', className: 'bg-indigo-100 text-indigo-800 border-indigo-200' },
  staff: { label: 'Staff', className: 'bg-red-100 text-red-800 border-red-200' },
  member: { label: 'Member', className: 'bg-teal-100 text-teal-800 border-teal-200' },
  guest: { label: 'Guest', className: 'bg-amber-100 text-amber-800 border-amber-200' },
  none: { label: 'Viewer', className: 'bg-gray-100 text-gray-600 border-gray-200' },
};

interface RoleBadgeProps {
  role: GMTableViewerRole;
}

function RoleBadge({ role }: RoleBadgeProps) {
  const { label, className } = ROLE_BADGE_VARIANTS[role];
  return (
    <Badge variant="outline" className={className}>
      {label}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
// TableCard
// ---------------------------------------------------------------------------

interface TableCardProps {
  table: GMTable;
}

export function TableCard({ table }: TableCardProps) {
  const navigate = useNavigate();

  function handleView() {
    void navigate(`/tables/${table.id}`);
  }

  return (
    <Card>
      <CardContent className="flex items-center justify-between gap-4 py-4">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-base font-semibold">{table.name}</span>
            <RoleBadge role={table.viewer_role} />
            {table.status === 'archived' && (
              <Badge variant="outline" className="bg-gray-100 text-gray-500">
                Archived
              </Badge>
            )}
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
            <span>GM: {table.gm_username}</span>
            <span>
              {table.member_count} member{table.member_count !== 1 ? 's' : ''}
            </span>
            <span>
              {table.story_count} stor{table.story_count !== 1 ? 'ies' : 'y'}
            </span>
          </div>
          {table.description && (
            <p className="mt-1 line-clamp-1 text-sm text-muted-foreground">{table.description}</p>
          )}
        </div>
        <Button variant="outline" size="sm" onClick={handleView}>
          View
        </Button>
      </CardContent>
    </Card>
  );
}
