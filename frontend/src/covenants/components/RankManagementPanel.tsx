/**
 * RankManagementPanel — manage the covenant's rank ladder.
 *
 * Only rendered when the viewer has can_manage_ranks capability. Shows a
 * sorted list of ranks (tier ascending = highest authority first) with
 * inline edit, reorder, delete, and a "Create Rank" form at the bottom.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import type { ViewerCapabilities, CovenantRank } from '@/covenants/api';
import {
  useCovenantRanks,
  useCreateRank,
  useUpdateRank,
  useDeleteRank,
  useReorderRanks,
} from '@/covenants/queries';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface RankManagementPanelProps {
  covenantId: number;
  viewerCapabilities: ViewerCapabilities;
}

// ---------------------------------------------------------------------------
// Inline edit state per-rank
// ---------------------------------------------------------------------------

interface EditState {
  name: string;
  can_invite: boolean;
  can_kick: boolean;
  can_manage_ranks: boolean;
}

// ---------------------------------------------------------------------------
// Delete confirmation popover (inline state machine)
// ---------------------------------------------------------------------------

interface DeleteConfirmProps {
  rank: CovenantRank;
  otherRanks: CovenantRank[];
  onConfirm: (reassignTo: number) => void;
  isPending: boolean;
}

function DeleteConfirm({ rank, otherRanks, onConfirm, isPending }: DeleteConfirmProps) {
  const [reassignTo, setReassignTo] = useState<number>(otherRanks[0]?.id ?? 0);
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button
          size="sm"
          variant="destructive"
          disabled={otherRanks.length === 0 || isPending}
          title={otherRanks.length === 0 ? 'Cannot delete the only rank' : undefined}
        >
          Delete
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>Delete rank "{rank.name}"?</AlertDialogTitle>
          <AlertDialogDescription>
            Members currently in this rank will be moved to the rank you choose below. This cannot
            be undone.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <div className="py-2">
          <label htmlFor={`reassign-select-${rank.id}`} className="mb-1 block text-sm font-medium">
            Reassign members to:
          </label>
          <select
            id={`reassign-select-${rank.id}`}
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={reassignTo}
            onChange={(e) => setReassignTo(Number(e.target.value))}
          >
            {otherRanks.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name} (tier {r.tier})
              </option>
            ))}
          </select>
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={() => onConfirm(reassignTo)} disabled={reassignTo === 0}>
            Delete
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

// ---------------------------------------------------------------------------
// RankRow — one rank in the ladder list
// ---------------------------------------------------------------------------

interface RankRowProps {
  rank: CovenantRank;
  allRanks: CovenantRank[];
  index: number;
  covenantId: number;
}

function RankRow({ rank, allRanks, index, covenantId }: RankRowProps) {
  const [editing, setEditing] = useState(false);
  const [editState, setEditState] = useState<EditState>({
    name: rank.name,
    can_invite: rank.can_invite ?? false,
    can_kick: rank.can_kick ?? false,
    can_manage_ranks: rank.can_manage_ranks ?? false,
  });

  const updateRank = useUpdateRank(covenantId);
  const deleteRank = useDeleteRank(covenantId);
  const reorderRanks = useReorderRanks(covenantId);

  const otherRanks = allRanks.filter((r) => r.id !== rank.id);
  const isFirst = index === 0;
  const isLast = index === allRanks.length - 1;

  function handleMoveUp() {
    const sorted = [...allRanks];
    const ids = sorted.map((r) => r.id);
    // Swap this rank with the one before it
    const tmp = ids[index - 1];
    ids[index - 1] = ids[index];
    ids[index] = tmp;
    reorderRanks.mutate({ orderedRankIds: ids });
  }

  function handleMoveDown() {
    const sorted = [...allRanks];
    const ids = sorted.map((r) => r.id);
    const tmp = ids[index + 1];
    ids[index + 1] = ids[index];
    ids[index] = tmp;
    reorderRanks.mutate({ orderedRankIds: ids });
  }

  function handleSaveEdit() {
    updateRank.mutate({ id: rank.id, data: editState }, { onSuccess: () => setEditing(false) });
  }

  function handleCancelEdit() {
    setEditState({
      name: rank.name,
      can_invite: rank.can_invite ?? false,
      can_kick: rank.can_kick ?? false,
      can_manage_ranks: rank.can_manage_ranks ?? false,
    });
    setEditing(false);
  }

  return (
    <div className="space-y-2 rounded-md border px-4 py-3" data-testid="rank-row">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-sm font-medium">
            {rank.name} <span className="text-xs text-muted-foreground">(tier {rank.tier})</span>
          </span>
          {rank.can_invite && (
            <Badge variant="outline" className="text-xs">
              can_invite
            </Badge>
          )}
          {rank.can_kick && (
            <Badge variant="outline" className="text-xs">
              can_kick
            </Badge>
          )}
          {rank.can_manage_ranks && (
            <Badge variant="outline" className="text-xs">
              can_manage_ranks
            </Badge>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <Button
            size="sm"
            variant="outline"
            onClick={handleMoveUp}
            disabled={isFirst || reorderRanks.isPending}
            aria-label="Move rank up"
          >
            Up
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleMoveDown}
            disabled={isLast || reorderRanks.isPending}
            aria-label="Move rank down"
          >
            Down
          </Button>
          <Button size="sm" variant="outline" onClick={() => setEditing((v) => !v)}>
            {editing ? 'Cancel' : 'Edit'}
          </Button>
          <DeleteConfirm
            rank={rank}
            otherRanks={otherRanks}
            onConfirm={(reassignTo) => deleteRank.mutate({ rankId: rank.id, reassignTo })}
            isPending={deleteRank.isPending}
          />
        </div>
      </div>

      {editing && (
        <div className="space-y-2 border-t pt-1">
          <Input
            value={editState.name}
            onChange={(e) => setEditState((s) => ({ ...s, name: e.target.value }))}
            placeholder="Rank name"
            className="h-8 text-sm"
          />
          <div className="flex flex-wrap gap-3 text-sm">
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={editState.can_invite}
                onChange={(e) => setEditState((s) => ({ ...s, can_invite: e.target.checked }))}
              />
              can_invite
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={editState.can_kick}
                onChange={(e) => setEditState((s) => ({ ...s, can_kick: e.target.checked }))}
              />
              can_kick
            </label>
            <label className="flex cursor-pointer items-center gap-1.5">
              <input
                type="checkbox"
                checked={editState.can_manage_ranks}
                onChange={(e) =>
                  setEditState((s) => ({ ...s, can_manage_ranks: e.target.checked }))
                }
              />
              can_manage_ranks
            </label>
          </div>
          <div className="flex gap-2">
            <Button
              size="sm"
              onClick={handleSaveEdit}
              disabled={updateRank.isPending || !editState.name.trim()}
            >
              {updateRank.isPending ? 'Saving…' : 'Save'}
            </Button>
            <Button size="sm" variant="outline" onClick={handleCancelEdit}>
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main panel
// ---------------------------------------------------------------------------

export function RankManagementPanel({ covenantId, viewerCapabilities }: RankManagementPanelProps) {
  const [newName, setNewName] = useState('');
  const { data: ranksPage } = useCovenantRanks(covenantId);
  const createRank = useCreateRank(covenantId);

  if (!viewerCapabilities.can_manage_ranks) return null;

  // Sort by tier ascending (tier 1 = highest authority = first in list)
  const ranks = [...(ranksPage?.results ?? [])].sort((a, b) => a.tier - b.tier);
  const nextTier = ranks.length > 0 ? Math.max(...ranks.map((r) => r.tier)) + 1 : 1;

  function handleCreate() {
    const trimmed = newName.trim();
    if (!trimmed) return;
    createRank.mutate(
      { covenant: covenantId, name: trimmed, tier: nextTier },
      { onSuccess: () => setNewName('') }
    );
  }

  return (
    <Card data-testid="rank-management-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Rank Ladder</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {ranks.length === 0 ? (
          <p className="py-2 text-sm text-muted-foreground">
            No ranks yet. Create the first rank below.
          </p>
        ) : (
          <div className="space-y-2">
            {ranks.map((rank, index) => (
              <RankRow
                key={rank.id}
                rank={rank}
                allRanks={ranks}
                index={index}
                covenantId={covenantId}
              />
            ))}
          </div>
        )}

        {/* Create rank form */}
        <div className="flex gap-2 border-t pt-2">
          <Input
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            placeholder="New rank name"
            className="h-8 text-sm"
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreate();
            }}
          />
          <Button
            size="sm"
            onClick={handleCreate}
            disabled={createRank.isPending || !newName.trim()}
          >
            {createRank.isPending ? 'Creating…' : 'Create'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
