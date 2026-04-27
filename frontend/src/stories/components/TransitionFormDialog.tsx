/**
 * TransitionFormDialog — create or edit a Transition from a source episode.
 *
 * Fields: target_episode (optional), mode, connection_type, connection_summary, order.
 * Also manages TransitionRequiredOutcome rows (routing predicate).
 *
 * Multi-roundtrip approach (Approach A):
 *  1. Save the transition via POST/PATCH.
 *  2. For each new routing row: POST /api/transition-required-outcomes/.
 *  3. For each removed routing row: DELETE /api/transition-required-outcomes/{id}/.
 * No backend transaction endpoint exists; partial saves are visible briefly.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Trash2, Plus } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import { Combobox } from '@/components/ui/combobox';
import {
  useCreateTransition,
  useUpdateTransition,
  useTransitionRequiredOutcomes,
  useCreateTransitionRequiredOutcome,
  useDeleteTransitionRequiredOutcome,
  useEpisodeList,
  useBeatList,
} from '../queries';
import type { Transition, TransitionRequiredOutcome } from '../types';

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  source_episode?: string[];
  target_episode?: string[];
  mode?: string[];
  connection_type?: string[];
  connection_summary?: string[];
  order?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const MODE_OPTIONS = [
  { value: 'auto', label: 'Auto — fires automatically when eligibility is satisfied' },
  { value: 'gm_choice', label: 'GM Choice — Lead GM picks from the eligible set' },
];

const CONNECTION_TYPE_OPTIONS = [
  { value: '', label: '(none)' },
  { value: 'therefore', label: 'Therefore' },
  { value: 'but', label: 'But' },
];

const OUTCOME_OPTIONS = [
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
  { value: 'expired', label: 'Expired' },
];

// ---------------------------------------------------------------------------
// Routing predicate row editor
// ---------------------------------------------------------------------------

interface AddRoutingRowProps {
  episodeId: number;
  onAdd: (beatId: number, outcome: string) => void;
  disabled: boolean;
}

function AddRoutingRow({ episodeId, onAdd, disabled }: AddRoutingRowProps) {
  const [beatId, setBeatId] = useState('');
  const [outcome, setOutcome] = useState('success');
  const [adding, setAdding] = useState(false);

  const { data: beatsData } = useBeatList({ episode: episodeId, page_size: 100 });
  const beatOptions =
    beatsData?.results.map((b) => ({
      value: String(b.id),
      label: `#${b.id}: ${b.internal_description?.slice(0, 50) ?? '(no description)'}`,
    })) ?? [];

  if (!adding) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-1 gap-1"
        onClick={() => setAdding(true)}
        disabled={disabled}
        data-testid="add-routing-row-btn"
      >
        <Plus className="h-3 w-3" />
        Add Condition
      </Button>
    );
  }

  return (
    <div
      className="mt-2 flex flex-col gap-2 rounded-md border p-3"
      data-testid="add-routing-row-form"
    >
      <div className="space-y-1">
        <Label className="text-xs">Beat</Label>
        <Combobox
          items={beatOptions}
          value={beatId}
          onValueChange={setBeatId}
          placeholder="Select beat…"
          searchPlaceholder="Search beats…"
          emptyMessage="No beats found."
        />
      </div>
      <div className="space-y-1">
        <Label className="text-xs">Required Outcome</Label>
        <Combobox
          items={OUTCOME_OPTIONS}
          value={outcome}
          onValueChange={setOutcome}
          placeholder="Select outcome…"
        />
      </div>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          onClick={() => {
            if (!beatId) return;
            onAdd(Number(beatId), outcome);
            setBeatId('');
            setOutcome('success');
            setAdding(false);
          }}
          disabled={!beatId}
          data-testid="confirm-routing-row"
        >
          Add
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Routing predicate manager (for existing transitions)
// ---------------------------------------------------------------------------

interface RoutingPredicateManagerProps {
  transition: Transition;
  episodeId: number;
}

function RoutingPredicateManager({ transition, episodeId }: RoutingPredicateManagerProps) {
  const { data, refetch } = useTransitionRequiredOutcomes({ transition: transition.id });
  const createMutation = useCreateTransitionRequiredOutcome();
  const deleteMutation = useDeleteTransitionRequiredOutcome();

  const rows = data?.results ?? [];

  function handleAdd(beatId: number, outcome: string) {
    const rowData: Omit<TransitionRequiredOutcome, 'id'> = {
      transition: transition.id,
      beat: beatId,
      required_outcome: outcome as TransitionRequiredOutcome['required_outcome'],
    };
    createMutation.mutate(rowData, {
      onSuccess: () => {
        void refetch();
        toast.success('Routing condition added');
      },
      onError: () => toast.error('Failed to add routing condition'),
    });
  }

  function handleDelete(row: TransitionRequiredOutcome) {
    deleteMutation.mutate(
      { id: row.id, transitionId: transition.id },
      {
        onSuccess: () => {
          void refetch();
          toast.success('Routing condition removed');
        },
        onError: () => toast.error('Failed to remove routing condition'),
      }
    );
  }

  return (
    <div className="space-y-2">
      {rows.length === 0 ? (
        <p className="text-sm italic text-muted-foreground" data-testid="routing-predicate-empty">
          No conditions — this transition is always eligible.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="routing-predicate-list">
          {rows.map((row) => (
            <li
              key={row.id}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              data-testid="routing-predicate-row"
            >
              <span>
                Beat #{row.beat} — {row.required_outcome}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                onClick={() => handleDelete(row)}
                disabled={deleteMutation.isPending}
                aria-label="Remove routing condition"
                data-testid="remove-routing-row-btn"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <AddRoutingRow episodeId={episodeId} onAdd={handleAdd} disabled={createMutation.isPending} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface TransitionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceEpisodeId: number;
  storyId: number;
  transition?: Transition;
  onSuccess?: (transition: Transition) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function TransitionFormDialog({
  open,
  onOpenChange,
  sourceEpisodeId,
  storyId,
  transition,
  onSuccess,
}: TransitionFormDialogProps) {
  const isEdit = transition !== undefined;

  const [targetEpisode, setTargetEpisode] = useState<string>(
    transition?.target_episode != null ? String(transition.target_episode) : ''
  );
  const [mode, setMode] = useState<string>(transition?.mode ?? 'auto');
  const [connectionType, setConnectionType] = useState<string>(transition?.connection_type ?? '');
  const [connectionSummary, setConnectionSummary] = useState(transition?.connection_summary ?? '');
  const [order, setOrder] = useState<string>(
    transition?.order !== undefined ? String(transition.order) : '0'
  );
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});
  const [savedTransition, setSavedTransition] = useState<Transition | undefined>(
    isEdit ? transition : undefined
  );

  const createMutation = useCreateTransition();
  const updateMutation = useUpdateTransition();
  const isPending = createMutation.isPending || updateMutation.isPending;

  // Load episodes in the same story for target selector
  const { data: episodesData } = useEpisodeList({ story: storyId, page_size: 100 });
  const episodeOptions =
    episodesData?.results
      .filter((ep) => ep.id !== sourceEpisodeId)
      .map((ep) => ({ value: String(ep.id), label: ep.title })) ?? [];

  function resetForm() {
    setTargetEpisode(transition?.target_episode != null ? String(transition.target_episode) : '');
    setMode(transition?.mode ?? 'auto');
    setConnectionType(transition?.connection_type ?? '');
    setConnectionSummary(transition?.connection_summary ?? '');
    setOrder(transition?.order !== undefined ? String(transition.order) : '0');
    setFieldErrors({});
    setSavedTransition(isEdit ? transition : undefined);
  }

  function handleOpenChange(next: boolean) {
    if (!next) resetForm();
    onOpenChange(next);
  }

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') setFieldErrors(data as DRFFieldErrors);
          })
          .catch(() => toast.error('An error occurred. Please try again.'));
        return;
      }
    }
    toast.error(err instanceof Error ? err.message : 'An error occurred. Please try again.');
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    const data: Partial<Transition> = {
      source_episode: sourceEpisodeId,
      target_episode: targetEpisode ? Number(targetEpisode) : null,
      mode: mode as Transition['mode'],
      connection_type: (connectionType || undefined) as Transition['connection_type'],
      connection_summary: connectionSummary.trim(),
      order: Number(order),
    };

    if (isEdit && transition) {
      updateMutation.mutate(
        { id: transition.id, data },
        {
          onSuccess: (updated) => {
            toast.success('Transition updated');
            setSavedTransition(updated);
            onSuccess?.(updated);
          },
          onError: handleError,
        }
      );
    } else {
      createMutation.mutate(data, {
        onSuccess: (created) => {
          toast.success('Transition created');
          setSavedTransition(created);
          onSuccess?.(created);
        },
        onError: handleError,
      });
    }
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-xl">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{isEdit ? 'Edit Transition' : 'Create Transition'}</DialogTitle>
          </DialogHeader>

          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Source episode — read-only */}
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Source episode ID: <span className="font-mono">{sourceEpisodeId}</span>
              </p>
            </div>

            {/* Target episode */}
            <div className="space-y-1.5">
              <Label>Target Episode</Label>
              <Combobox
                items={episodeOptions}
                value={targetEpisode}
                onValueChange={setTargetEpisode}
                placeholder="Advance to frontier (no next episode)"
                searchPlaceholder="Search episodes…"
                emptyMessage="No episodes found."
                allowDeselect
              />
              <p className="text-xs text-muted-foreground">
                Leave blank to advance to the authoring frontier.
              </p>
              {fieldErrors.target_episode && (
                <p className="text-xs text-destructive">{fieldErrors.target_episode.join(' ')}</p>
              )}
            </div>

            {/* Mode */}
            <div className="space-y-2">
              <Label>Mode</Label>
              <RadioGroup value={mode} onValueChange={setMode} className="flex flex-col gap-1">
                {MODE_OPTIONS.map(({ value, label }) => (
                  <label
                    key={value}
                    className="flex cursor-pointer items-center gap-3 rounded-md border p-2.5 text-sm hover:bg-accent"
                  >
                    <RadioGroupItem value={value} id={`mode-${value}`} />
                    <span>{label}</span>
                  </label>
                ))}
              </RadioGroup>
              {fieldErrors.mode && (
                <p className="text-xs text-destructive">{fieldErrors.mode.join(' ')}</p>
              )}
            </div>

            {/* Connection type */}
            <div className="space-y-1.5">
              <Label>Connection Type</Label>
              <Combobox
                items={CONNECTION_TYPE_OPTIONS}
                value={connectionType}
                onValueChange={setConnectionType}
                placeholder="(none)"
              />
              {fieldErrors.connection_type && (
                <p className="text-xs text-destructive">{fieldErrors.connection_type.join(' ')}</p>
              )}
            </div>

            {/* Connection summary */}
            <div className="space-y-1.5">
              <Label htmlFor="transition-connection-summary">Connection Summary</Label>
              <Textarea
                id="transition-connection-summary"
                value={connectionSummary}
                onChange={(e) => setConnectionSummary(e.target.value)}
                placeholder="Why does this transition fire…"
                rows={2}
              />
              {fieldErrors.connection_summary && (
                <p className="text-xs text-destructive">
                  {fieldErrors.connection_summary.join(' ')}
                </p>
              )}
            </div>

            {/* Order */}
            <div className="space-y-1.5">
              <Label htmlFor="transition-order">Order (tie-breaking)</Label>
              <Input
                id="transition-order"
                type="number"
                min={0}
                value={order}
                onChange={(e) => setOrder(e.target.value)}
                placeholder="0"
              />
              {fieldErrors.order && (
                <p className="text-xs text-destructive">{fieldErrors.order.join(' ')}</p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={isPending}>
              {isPending
                ? isEdit
                  ? 'Saving…'
                  : 'Creating…'
                : isEdit
                  ? 'Save Transition'
                  : 'Create Transition'}
            </Button>
          </DialogFooter>
        </form>

        {/* Routing Predicate — available once transition is saved */}
        {savedTransition ? (
          <div className="mt-6 border-t pt-4">
            <p className="mb-1 text-sm font-medium">Routing Predicate</p>
            <p className="mb-3 text-xs text-muted-foreground">
              Add beat-outcome conditions that must all be true for this transition to fire.
            </p>
            <RoutingPredicateManager transition={savedTransition} episodeId={sourceEpisodeId} />
          </div>
        ) : (
          <p className="mt-4 text-xs text-muted-foreground">
            Save the transition first to add routing conditions.
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
