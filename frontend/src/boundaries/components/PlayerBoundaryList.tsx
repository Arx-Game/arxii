/**
 * PlayerBoundaryList — the player's own hard lines + advisories (#1771).
 * Account-wide (owner = PlayerData), not tied to a specific character.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { usePlayerBoundaries, useDeletePlayerBoundary, useContentThemes } from '../queries';
import { PlayerBoundaryFormDialog } from './PlayerBoundaryFormDialog';
import type { PlayerBoundary } from '../types';

export function PlayerBoundaryList() {
  const { data: boundaries, isLoading } = usePlayerBoundaries();
  const { data: themes } = useContentThemes();
  const deleteMutation = useDeletePlayerBoundary();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<PlayerBoundary | undefined>(undefined);
  const [pendingDelete, setPendingDelete] = useState<PlayerBoundary | null>(null);

  function themeName(themeId: number | null | undefined): string | null {
    if (themeId == null) return null;
    return themes?.results.find((t) => t.id === themeId)?.name ?? null;
  }

  function openCreate() {
    setEditing(undefined);
    setFormOpen(true);
  }

  function openEdit(boundary: PlayerBoundary) {
    setEditing(boundary);
    setFormOpen(true);
  }

  if (isLoading) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-10 w-full" />
      </div>
    );
  }

  const rows = boundaries?.results ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Hard lines are auto-blocked from stakes and always private. Advisories can optionally be
          shared with scene partners.
        </p>
        <Button size="sm" onClick={openCreate}>
          Add boundary
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No boundaries set yet.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((b) => (
            <li
              key={b.id}
              className="flex items-center justify-between gap-3 rounded-md border bg-card p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant={b.kind === 'hard_line' ? 'destructive' : 'secondary'}>
                    {b.kind === 'hard_line' ? 'Hard line' : 'Advisory'}
                  </Badge>
                  {themeName(b.theme) && (
                    <span className="text-sm font-medium">{themeName(b.theme)}</span>
                  )}
                </div>
                {b.detail && b.kind === 'advisory' && (
                  <p className="mt-1 truncate text-sm text-muted-foreground">{b.detail}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => openEdit(b)}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPendingDelete(b)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <PlayerBoundaryFormDialog open={formOpen} onOpenChange={setFormOpen} boundary={editing} />

      <AlertDialog
        open={pendingDelete != null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this boundary?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPendingDelete(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingDelete) deleteMutation.mutate(pendingDelete.id);
                setPendingDelete(null);
              }}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
