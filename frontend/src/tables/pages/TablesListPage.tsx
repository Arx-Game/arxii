/**
 * TablesListPage — list of GM tables visible to the current user.
 *
 * Tables are sectioned by viewer_role:
 *   - Tables I run (viewer_role === 'gm')
 *   - Tables I'm a member of (viewer_role === 'member')
 *   - Tables I have stories at (viewer_role === 'guest')
 *   - Staff: all tables (if "Show all" toggle is active)
 *
 * GM users see a "+ Create Table" button. Non-GMs do not.
 *
 * Whether a user is a GM is determined by checking if any table returns
 * viewer_role === 'gm'. The account endpoint does not expose GMProfile
 * membership — see stores/auth and the Stories CLAUDE.md for the known gotcha.
 * A dedicated GMProfile check is deferred to Wave 11 when routing is wired.
 */

import { useState } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { useSelector } from 'react-redux';
import type { RootState } from '@/store/store';
import { useTables } from '../queries';
import { TableCard } from '../components/TableCard';
import { TableFormDialog } from '../components/TableFormDialog';
import type { GMTable, GMTableViewerRole } from '../types';

// ---------------------------------------------------------------------------
// Loading skeletons
// ---------------------------------------------------------------------------

function TableCardSkeleton() {
  return (
    <div className="animate-pulse rounded-lg border bg-card p-4" data-testid="table-card-skeleton">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 space-y-2">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-48" />
            <Skeleton className="h-5 w-16" />
          </div>
          <div className="flex gap-3">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-4 w-20" />
            <Skeleton className="h-4 w-20" />
          </div>
        </div>
        <Skeleton className="h-8 w-14" />
      </div>
    </div>
  );
}

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <TableCardSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Section component
// ---------------------------------------------------------------------------

interface TableSectionProps {
  title: string;
  tables: GMTable[];
  emptyMessage: string;
}

function TableSection({ title, tables, emptyMessage }: TableSectionProps) {
  if (tables.length === 0) {
    return (
      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-muted-foreground">{title}</h2>
        <p className="py-4 text-center text-sm text-muted-foreground">{emptyMessage}</p>
      </section>
    );
  }
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold text-muted-foreground">{title}</h2>
      {tables.map((table) => (
        <TableCard key={table.id} table={table} />
      ))}
    </section>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function TablesListInner() {
  const [showAll, setShowAll] = useState(false);

  // Fetch all visible tables — backend already scopes to tables where the
  // viewer has a relationship (member, GM, participant, staff).
  const { data, isLoading } = useTables();

  // Staff detection from Redux auth slice
  const isStaff = useSelector((state: RootState) => state.auth.account?.is_staff ?? false);

  if (isLoading) return <LoadingSkeletons />;

  const allTables = data?.results ?? [];

  // Partition by viewer_role
  const byRole = (role: GMTableViewerRole) => allTables.filter((t) => t.viewer_role === role);

  const gmTables = byRole('gm');
  const staffTables = byRole('staff');
  const memberTables = byRole('member');
  const guestTables = byRole('guest');
  const otherTables = byRole('none');

  // A user is a GM if they own at least one table
  const isGM = gmTables.length > 0;

  // The GM profile ID needed for table creation. Since we can only determine
  // this from the API (not the auth slice), we look it up from the first table
  // owned by this user. If no tables exist yet, creation will use a placeholder
  // that causes a 400 — Wave 11 should fetch GMProfile from a dedicated endpoint.
  // For now, display the create button for any user who is already a GM.
  const gmProfileId = gmTables[0]?.gm ?? 0;

  return (
    <div className="space-y-8">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <div />
        {isGM && (
          <TableFormDialog mode="create" gmProfileId={gmProfileId}>
            <Button size="sm">+ Create Table</Button>
          </TableFormDialog>
        )}
      </div>

      {/* Staff toggle */}
      {isStaff && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowAll((v) => !v)}
            className={`rounded-full border px-3 py-1 text-sm font-medium transition-colors ${
              showAll
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-accent'
            }`}
          >
            {showAll ? 'Showing all tables' : 'Show all tables (staff)'}
          </button>
        </div>
      )}

      {/* Sections */}
      {gmTables.length > 0 && (
        <TableSection
          title="Tables I Run"
          tables={gmTables}
          emptyMessage="You don't run any tables yet."
        />
      )}
      {staffTables.length > 0 && (
        <TableSection title="Tables (Staff View)" tables={staffTables} emptyMessage="" />
      )}
      <TableSection
        title="Tables I'm a Member Of"
        tables={memberTables}
        emptyMessage="You're not a member of any tables."
      />
      <TableSection
        title="Tables I Have Stories At"
        tables={guestTables}
        emptyMessage="You don't have stories at any external tables."
      />
      {showAll && otherTables.length > 0 && (
        <TableSection
          title="All Other Tables"
          tables={otherTables}
          emptyMessage="No other tables."
        />
      )}

      {/* Total empty state */}
      {allTables.length === 0 && (
        <p className="py-8 text-center text-muted-foreground">
          No tables found. Ask a GM to invite you, or create your own if you have a GM profile.
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function TablesListPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">Tables</h1>
      <ErrorBoundary>
        <TablesListInner />
      </ErrorBoundary>
    </div>
  );
}
