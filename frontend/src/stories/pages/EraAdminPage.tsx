/**
 * EraAdminPage — staff admin page for era (season) lifecycle management.
 *
 * Route: /stories/eras (StaffRoute wrapper added in Wave 11)
 * Permission gating: EraViewSet 403s for non-staff on write ops;
 *   throwOnError: false renders a friendly access-denied for non-staff.
 *
 * Layout:
 *   1. Page header with "+ Create Era" button
 *   2. EraTimeline visualization
 *   3. List with per-era detail rows (status, dates, story_count, actions)
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useEras } from '../queries';
import { EraTimeline } from '../components/EraTimeline';
import { EraStatusBadge } from '../components/EraStatusBadge';
import { EraFormDialog } from '../components/EraFormDialog';
import { AdvanceEraDialog } from '../components/AdvanceEraDialog';
import { ArchiveEraDialog } from '../components/ArchiveEraDialog';
import type { Era } from '../types';

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function PageSkeleton() {
  return (
    <div className="space-y-4" data-testid="era-page-skeleton">
      <Skeleton className="h-8 w-64" />
      <Skeleton className="h-24 w-full" />
      {[1, 2, 3].map((i) => (
        <Skeleton key={i} className="h-16 w-full" />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Per-era detail row
// ---------------------------------------------------------------------------

interface EraRowProps {
  era: Era;
  isHighlighted: boolean;
  onEdit: (era: Era) => void;
  onAdvance: (era: Era) => void;
  onArchive: (era: Era) => void;
  onDelete: (era: Era) => void;
}

function EraRow({ era, isHighlighted, onEdit, onAdvance, onArchive, onDelete }: EraRowProps) {
  return (
    <div
      id={`era-row-${era.id}`}
      data-testid={`era-row-${era.id}`}
      className={`rounded-lg border p-4 transition-colors ${
        isHighlighted ? 'border-primary bg-primary/5' : 'border-border bg-card'
      }`}
    >
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-muted-foreground">
              Season {era.season_number}
            </span>
            <EraStatusBadge status={era.status} />
          </div>
          <div className="text-base font-semibold">{era.display_name}</div>
          <div className="font-mono text-xs text-muted-foreground">{era.name}</div>
          {era.description && (
            <p className="line-clamp-2 text-sm text-muted-foreground">{era.description}</p>
          )}
          <div className="flex gap-4 text-xs text-muted-foreground">
            <span>
              {era.story_count} {era.story_count === 1 ? 'story' : 'stories'}
            </span>
            {era.activated_at && (
              <span>Activated: {new Date(era.activated_at).toLocaleDateString()}</span>
            )}
            {era.concluded_at && (
              <span>Concluded: {new Date(era.concluded_at).toLocaleDateString()}</span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant="outline" onClick={() => onEdit(era)}>
            Edit
          </Button>
          {era.status === 'upcoming' && (
            <Button size="sm" variant="outline" onClick={() => onAdvance(era)}>
              Advance
            </Button>
          )}
          {(era.status === 'active' || era.status === 'concluded') && (
            <Button size="sm" variant="outline" onClick={() => onArchive(era)}>
              Archive
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            className="text-destructive hover:text-destructive"
            onClick={() => onDelete(era)}
          >
            Delete
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export function EraAdminPage() {
  const erasQuery = useEras({ ordering: 'season_number', page_size: 100 });

  const [createOpen, setCreateOpen] = useState(false);
  const [editEra, setEditEra] = useState<Era | null>(null);
  const [advanceEra, setAdvanceEra] = useState<Era | null>(null);
  const [archiveEra, setArchiveEra] = useState<Era | null>(null);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  function handleSelectEra(id: number) {
    setSelectedId(id);
    const el = document.getElementById(`era-row-${id}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  function handleDelete(era: Era) {
    // Simple confirmation — full delete dialog can be added later.
    if (window.confirm(`Delete Era "${era.display_name}"? This cannot be undone.`)) {
      // TODO: wire useDeleteEra once confirm UX is finalized
    }
  }

  if (erasQuery.isPending) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <PageSkeleton />
      </div>
    );
  }

  if (erasQuery.isError) {
    return (
      <div className="container mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <p className="text-sm text-destructive">
          Failed to load eras. You may not have permission to view this page.
        </p>
      </div>
    );
  }

  const eras = erasQuery.data?.results ?? [];
  const sorted = [...eras].sort((a, b) => a.season_number - b.season_number);

  return (
    <div className="container mx-auto max-w-4xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      {/* Header */}
      <div className="mb-6 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">Eras (Seasons)</h1>
          <p className="text-sm text-muted-foreground">
            Manage the metaplot era lifecycle. Only staff can advance or archive eras.
          </p>
        </div>
        <Button onClick={() => setCreateOpen(true)} data-testid="create-era-button">
          + Create Era
        </Button>
      </div>

      {/* Timeline */}
      {sorted.length > 0 && (
        <div className="mb-6 rounded-lg border bg-card p-4">
          <h2 className="mb-3 text-sm font-medium text-muted-foreground">Timeline</h2>
          <EraTimeline eras={sorted} selectedId={selectedId} onSelectEra={handleSelectEra} />
        </div>
      )}

      {/* Era list */}
      <div className="space-y-3" data-testid="era-list">
        {sorted.length === 0 ? (
          <div className="rounded-lg border border-dashed p-8 text-center">
            <p className="text-sm text-muted-foreground">No eras defined yet.</p>
            <Button variant="outline" className="mt-3" onClick={() => setCreateOpen(true)}>
              Create the first era
            </Button>
          </div>
        ) : (
          sorted.map((era) => (
            <EraRow
              key={era.id}
              era={era}
              isHighlighted={era.id === selectedId}
              onEdit={setEditEra}
              onAdvance={setAdvanceEra}
              onArchive={setArchiveEra}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>

      {/* Dialogs */}
      <EraFormDialog
        open={createOpen || editEra !== null}
        era={editEra}
        onClose={() => {
          setCreateOpen(false);
          setEditEra(null);
        }}
      />
      <AdvanceEraDialog
        open={advanceEra !== null}
        era={advanceEra}
        onClose={() => setAdvanceEra(null)}
      />
      <ArchiveEraDialog
        open={archiveEra !== null}
        era={archiveEra}
        onClose={() => setArchiveEra(null)}
      />
    </div>
  );
}
