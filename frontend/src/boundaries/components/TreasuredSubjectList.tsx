/**
 * TreasuredSubjectList — flag/list a character's treasured subjects (#1771).
 * Per-tenure (owner = RosterTenure): pass the selected character's tenure id.
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
import { useTreasuredSubjects, useDeleteTreasuredSubject } from '../queries';
import { TreasuredSubjectFormDialog } from './TreasuredSubjectFormDialog';
import type { TreasuredSubject } from '../types';

interface Props {
  tenureId: number;
}

export function TreasuredSubjectList({ tenureId }: Props) {
  const { data: subjects, isLoading } = useTreasuredSubjects(tenureId);
  const deleteMutation = useDeleteTreasuredSubject();

  const [formOpen, setFormOpen] = useState(false);
  const [editing, setEditing] = useState<TreasuredSubject | undefined>(undefined);
  const [pendingDelete, setPendingDelete] = useState<TreasuredSubject | null>(null);

  function openCreate() {
    setEditing(undefined);
    setFormOpen(true);
  }

  function openEdit(subject: TreasuredSubject) {
    setEditing(subject);
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

  const rows = subjects?.results ?? [];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Things this character treasures — staking one of these in a scene requires your pre-scene
          sign-off.
        </p>
        <Button size="sm" onClick={openCreate}>
          Flag a treasured subject
        </Button>
      </div>

      {rows.length === 0 ? (
        <p className="text-sm text-muted-foreground">No treasured subjects flagged yet.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-3 rounded-md border bg-card p-3"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <Badge variant="secondary">{s.subject_kind}</Badge>
                  <span className="text-sm font-medium">{s.subject_label}</span>
                </div>
                {s.detail && (
                  <p className="mt-1 truncate text-sm text-muted-foreground">{s.detail}</p>
                )}
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <Button size="sm" variant="ghost" onClick={() => openEdit(s)}>
                  Edit
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setPendingDelete(s)}>
                  Delete
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <TreasuredSubjectFormDialog
        open={formOpen}
        onOpenChange={setFormOpen}
        tenureId={tenureId}
        subject={editing}
      />

      <AlertDialog
        open={pendingDelete != null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this treasured subject?</AlertDialogTitle>
            <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel onClick={() => setPendingDelete(null)}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (pendingDelete) {
                  deleteMutation.mutate({ id: pendingDelete.id, tenureId });
                }
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
