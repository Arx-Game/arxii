/**
 * TableDetailPage — full detail view for a single GM table.
 *
 * Route: /tables/:id (wired by Wave 11)
 *
 * Tabs:
 *  - Stories: role-aware story list
 *  - Members: role-aware member roster
 *  - Bulletin: placeholder ("Bulletin board coming soon")
 *
 * GM/staff viewers see all content + admin actions.
 * Member/guest viewers see scoped content and no admin actions.
 *
 * Dialogs mounted here: Edit, Invite, Remove member, Leave, Archive.
 */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { useTable } from '../queries';
import { TableStoryRoster } from '../components/TableStoryRoster';
import { TableMemberRoster } from '../components/TableMemberRoster';
import { TableFormDialog } from '../components/TableFormDialog';
import { InviteToTableDialog } from '../components/InviteToTableDialog';
import { RemoveFromTableDialog } from '../components/RemoveFromTableDialog';
import { LeaveTableDialog } from '../components/LeaveTableDialog';
import { ArchiveTableDialog } from '../components/ArchiveTableDialog';
import { TableBulletin } from '../components/TableBulletin';

// ---------------------------------------------------------------------------
// Inner detail (inside error boundary)
// ---------------------------------------------------------------------------

function TableDetailInner({ tableId }: { tableId: number }) {
  const { data: table, isLoading } = useTable(tableId);

  // Dialog state
  const [removeOpen, setRemoveOpen] = useState(false);
  const [removeMembership, setRemoveMembership] = useState<{
    id: number;
    name: string;
  } | null>(null);
  const [leaveOpen, setLeaveOpen] = useState(false);
  const [archiveOpen, setArchiveOpen] = useState(false);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-4 w-48" />
        <div className="flex gap-4">
          <Skeleton className="h-16 w-28 rounded-lg" />
          <Skeleton className="h-16 w-28 rounded-lg" />
        </div>
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (!table) {
    return <p className="py-8 text-center text-muted-foreground">Table not found.</p>;
  }

  const isGMOrStaff = table.viewer_role === 'gm' || table.viewer_role === 'staff';
  const isMemberOrAbove =
    table.viewer_role === 'gm' || table.viewer_role === 'staff' || table.viewer_role === 'member';

  // My membership ID is needed for "leave" — we can only derive it if the
  // viewer is a member. The membership list will surface it when rendered.
  // For simplicity, the Leave button is shown but delegates the ID lookup
  // to TableMemberRoster's onRemove callback (which we repurpose as "leave").
  // TODO: pass viewer_membership_id from the backend for cleaner UX.

  function handleRemoveMember(membershipId: number, personaName: string) {
    setRemoveMembership({ id: membershipId, name: personaName });
    setRemoveOpen(true);
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-bold">{table.name}</h1>
            {table.status === 'archived' && (
              <Badge variant="outline" className="bg-gray-100 text-gray-500">
                Archived
              </Badge>
            )}
          </div>
          <p className="mt-1 text-muted-foreground">GM: {table.gm_username}</p>
          {table.description && (
            <p className="mt-2 text-sm text-muted-foreground">{table.description}</p>
          )}
        </div>

        {/* Admin actions (GM/staff only) */}
        {isGMOrStaff && (
          <div className="flex flex-wrap gap-2">
            <TableFormDialog mode="edit" table={table}>
              <Button variant="outline" size="sm">
                Edit
              </Button>
            </TableFormDialog>
            <InviteToTableDialog table={table}>
              <Button variant="outline" size="sm">
                Invite
              </Button>
            </InviteToTableDialog>
            {table.status === 'active' && (
              <Button
                variant="outline"
                size="sm"
                className="text-destructive hover:bg-destructive/10"
                onClick={() => setArchiveOpen(true)}
              >
                Archive
              </Button>
            )}
          </div>
        )}

        {/* Leave button (member/guest only) */}
        {(table.viewer_role === 'member' || table.viewer_role === 'guest') && (
          <Button
            variant="outline"
            size="sm"
            className="text-destructive hover:bg-destructive/10"
            onClick={() => setLeaveOpen(true)}
          >
            Leave Table
          </Button>
        )}
      </div>

      {/* Stats strip */}
      <div className="flex flex-wrap gap-4">
        <div className="rounded-lg border bg-card px-4 py-3 text-center">
          <p className="text-2xl font-bold">{table.member_count}</p>
          <p className="text-xs text-muted-foreground">
            {table.member_count === 1 ? 'Member' : 'Members'}
          </p>
        </div>
        <div className="rounded-lg border bg-card px-4 py-3 text-center">
          <p className="text-2xl font-bold">{table.story_count}</p>
          <p className="text-xs text-muted-foreground">
            {table.story_count === 1 ? 'Story' : 'Stories'}
          </p>
        </div>
      </div>

      {/* Tabs — overflow-x-auto so tab bar scrolls horizontally on very narrow screens */}
      <Tabs defaultValue="stories">
        <div className="overflow-x-auto">
          <TabsList>
            <TabsTrigger value="stories">Stories</TabsTrigger>
            <TabsTrigger value="members">Members</TabsTrigger>
            <TabsTrigger value="bulletin">Bulletin</TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="stories" className="mt-4">
          <TableStoryRoster
            table={table}
            onRemove={
              isGMOrStaff
                ? (_storyId, _storyTitle) => {
                    // Detach-from-table action — deferred to Wave 5 backend wiring.
                    // TODO: implement detach-from-table story removal dialog
                  }
                : undefined
            }
          />
        </TabsContent>

        <TabsContent value="members" className="mt-4">
          <TableMemberRoster
            table={table}
            onRemove={isGMOrStaff ? handleRemoveMember : undefined}
          />

          {/* "Other personas in stories I'm in" — deferred cross-reference */}
          {isMemberOrAbove && !isGMOrStaff && (
            <div className="mt-6 border-t pt-4">
              <p className="text-sm text-muted-foreground">
                Other personas in your stories at this table are shown above.
                {/* TODO: cross-reference StoryParticipation to filter — Wave 5 */}
              </p>
            </div>
          )}
        </TabsContent>

        <TabsContent value="bulletin" className="mt-4">
          <TableBulletin table={table} />
        </TabsContent>
      </Tabs>

      {/* Dialogs */}
      {removeMembership && (
        <RemoveFromTableDialog
          tableId={table.id}
          tableName={table.name}
          membershipId={removeMembership.id}
          personaName={removeMembership.name}
          open={removeOpen}
          onOpenChange={(next) => {
            setRemoveOpen(next);
            if (!next) setRemoveMembership(null);
          }}
        />
      )}

      <LeaveTableDialog
        tableId={table.id}
        tableName={table.name}
        membershipId={0} /* TODO: derive from viewer's active membership */
        open={leaveOpen}
        onOpenChange={setLeaveOpen}
      />

      <ArchiveTableDialog
        tableId={table.id}
        tableName={table.name}
        open={archiveOpen}
        onOpenChange={setArchiveOpen}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function TableDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tableId = id ? parseInt(id, 10) : 0;

  if (!tableId || isNaN(tableId)) {
    return (
      <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <p className="text-muted-foreground">Invalid table ID.</p>
      </div>
    );
  }

  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <ErrorBoundary>
        <TableDetailInner tableId={tableId} />
      </ErrorBoundary>
    </div>
  );
}
