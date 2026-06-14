/**
 * PromoteRoleDialog — controlled dialog for promoting a membership into one of
 * its current role's sub-roles.
 *
 * The membership's current role (membership.covenant_role) is the parent role;
 * useSubroles(parentRoleId) lists the sub-roles it can be promoted into. The
 * member picks one, and Promote dispatches usePromoteMembership.mutate. On
 * success the dialog closes; on a backend 400 the error `detail` (surfaced as
 * the rejected Error's message by the api layer) is shown inline.
 *
 * Parent owns the open state (C9 mounts this from the member row).
 */

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useSubroles, usePromoteMembership } from '@/covenants/queries';
import type { CharacterCovenantRole } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PromoteRoleDialogProps {
  covenantId: number;
  membership: CharacterCovenantRole;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PromoteRoleDialog({
  covenantId,
  membership,
  open,
  onOpenChange,
}: PromoteRoleDialogProps) {
  const parentRole = membership.covenant_role;
  const { data: subroles, isLoading } = useSubroles(parentRole.id);
  const promote = usePromoteMembership(covenantId);

  const [selectedId, setSelectedId] = useState<number | null>(null);

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setSelectedId(null);
      promote.reset();
    }
  }

  function handlePromote() {
    if (selectedId == null) return;
    promote.mutate(
      { membershipId: membership.id, targetSubroleId: selectedId },
      {
        onSuccess: () => handleOpenChange(false),
      }
    );
  }

  const list = subroles ?? [];
  const hasSubroles = list.length > 0;
  const errorMessage =
    promote.isError && promote.error instanceof Error ? promote.error.message : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Promote {parentRole.name}</DialogTitle>
          <DialogDescription>Choose a sub-role to unlock for this member.</DialogDescription>
        </DialogHeader>

        {errorMessage && (
          <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
            <p>{errorMessage}</p>
          </div>
        )}

        <div className="mt-4">
          {isLoading ? (
            <p className="py-4 text-sm text-muted-foreground">Loading sub-roles…</p>
          ) : !hasSubroles ? (
            <p className="py-4 text-sm text-muted-foreground">No sub-roles available.</p>
          ) : (
            <ul className="space-y-2" role="radiogroup" aria-label="Available sub-roles">
              {list.map((subrole) => {
                const selected = selectedId === subrole.id;
                return (
                  <li key={subrole.id}>
                    <button
                      type="button"
                      role="radio"
                      aria-checked={selected}
                      onClick={() => setSelectedId(subrole.id)}
                      disabled={promote.isPending}
                      className={
                        'w-full rounded-md border px-3 py-2 text-left transition-colors ' +
                        (selected ? 'border-primary bg-accent' : 'border-border hover:bg-accent/50')
                      }
                    >
                      <span className="block text-sm font-medium">{subrole.name}</span>
                      {subrole.description && (
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          {subrole.description}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {hasSubroles && (
          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={promote.isPending}
            >
              Cancel
            </Button>
            <Button
              type="button"
              onClick={handlePromote}
              disabled={selectedId == null || promote.isPending}
            >
              {promote.isPending ? 'Promoting…' : 'Promote'}
            </Button>
          </DialogFooter>
        )}
      </DialogContent>
    </Dialog>
  );
}
