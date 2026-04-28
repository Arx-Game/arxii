/**
 * TransitionFormDialog — create or edit a Transition from a source episode.
 *
 * Wave 13: Replaced the Phase 4 multi-roundtrip submit (POST transition →
 * N × POST outcomes) with a single atomic call to
 * POST /api/transitions/save-with-outcomes/.
 *
 * Routing predicates are now collected locally in state; on submit they are
 * sent together with the transition fields in one request.  If the server
 * rolls back (e.g. DB integrity error), no partial state is left behind.
 *
 * Fields: target_episode (optional), mode, connection_type, connection_summary,
 * order, and a routing predicate list (beat + required_outcome pairs).
 */

import { useState, useEffect } from 'react';
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
  useSaveTransitionWithOutcomes,
  useTransitionRequiredOutcomes,
  useEpisodeList,
  useBeatList,
} from '../queries';
import type { Transition } from '../types';

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
  outcomes?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Local routing predicate row (not yet persisted)
// ---------------------------------------------------------------------------

interface RoutingRow {
  /** Unique client-side key for React list rendering. */
  key: string;
  beatId: number;
  outcome: string;
  beatLabel: string;
}

let rowCounter = 0;
function nextKey(): string {
  rowCounter += 1;
  return `r${rowCounter}`;
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
// Add-routing-row sub-form
// ---------------------------------------------------------------------------

interface AddRoutingRowProps {
  episodeId: number;
  onAdd: (row: Omit<RoutingRow, 'key'>) => void;
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
            const beatLabel =
              beatOptions.find((o) => o.value === beatId)?.label ?? `Beat #${beatId}`;
            onAdd({ beatId: Number(beatId), outcome, beatLabel });
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
// Props
// ---------------------------------------------------------------------------

interface TransitionFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  sourceEpisodeId: number;
  storyId: number;
  transition?: Transition;
  /**
   * Pre-fill the target episode selector (used when opening from the DAG
   * drag-to-connect gesture so the user only needs to confirm, not re-select).
   */
  defaultTargetEpisodeId?: number;
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
  defaultTargetEpisodeId,
  onSuccess,
}: TransitionFormDialogProps) {
  const isEdit = transition !== undefined;

  const [targetEpisode, setTargetEpisode] = useState<string>(
    transition?.target_episode != null
      ? String(transition.target_episode)
      : defaultTargetEpisodeId != null
        ? String(defaultTargetEpisodeId)
        : ''
  );
  const [mode, setMode] = useState<string>(transition?.mode ?? 'auto');
  const [connectionType, setConnectionType] = useState<string>(transition?.connection_type ?? '');
  const [connectionSummary, setConnectionSummary] = useState(transition?.connection_summary ?? '');
  const [order, setOrder] = useState<string>(
    transition?.order !== undefined ? String(transition.order) : '0'
  );
  const [routingRows, setRoutingRows] = useState<RoutingRow[]>([]);
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  // For edit mode: load existing routing predicates once so the user can see and
  // remove them before submitting.  We do this once on open so the local state
  // starts with the server's current predicates.
  const existingOutcomesQuery = useTransitionRequiredOutcomes(
    isEdit && transition ? { transition: transition.id, page_size: 100 } : undefined
  );

  // Load episodes in the same story for target selector.
  const { data: episodesData } = useEpisodeList({ story: storyId, page_size: 100 });
  const episodeOptions =
    episodesData?.results
      .filter((ep) => ep.id !== sourceEpisodeId)
      .map((ep) => ({ value: String(ep.id), label: ep.title })) ?? [];

  // Populate routingRows from server data on first load in edit mode.
  const [initialised, setInitialised] = useState(false);
  useEffect(() => {
    if (!initialised && isEdit && existingOutcomesQuery.data) {
      const rows: RoutingRow[] = existingOutcomesQuery.data.results.map((row) => ({
        key: nextKey(),
        beatId: row.beat,
        outcome: row.required_outcome,
        beatLabel: `Beat #${row.beat}`,
      }));
      setRoutingRows(rows);
      setInitialised(true);
    }
  }, [initialised, isEdit, existingOutcomesQuery.data]);

  const saveMutation = useSaveTransitionWithOutcomes();
  const isPending = saveMutation.isPending;

  function resetForm() {
    setTargetEpisode(
      transition?.target_episode != null
        ? String(transition.target_episode)
        : defaultTargetEpisodeId != null
          ? String(defaultTargetEpisodeId)
          : ''
    );
    setMode(transition?.mode ?? 'auto');
    setConnectionType(transition?.connection_type ?? '');
    setConnectionSummary(transition?.connection_summary ?? '');
    setOrder(transition?.order !== undefined ? String(transition.order) : '0');
    setRoutingRows([]);
    setFieldErrors({});
    setInitialised(false);
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

  function handleAddRow(row: Omit<RoutingRow, 'key'>) {
    setRoutingRows((prev) => [...prev, { ...row, key: nextKey() }]);
  }

  function handleRemoveRow(key: string) {
    setRoutingRows((prev) => prev.filter((r) => r.key !== key));
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setFieldErrors({});

    saveMutation.mutate(
      {
        source_episode: sourceEpisodeId,
        target_episode: targetEpisode ? Number(targetEpisode) : null,
        mode,
        connection_type: connectionType,
        connection_summary: connectionSummary.trim(),
        order: Number(order),
        outcomes: routingRows.map((r) => ({
          beat: r.beatId,
          required_outcome: r.outcome,
        })),
        existing_id: isEdit && transition ? transition.id : null,
      },
      {
        onSuccess: (saved) => {
          toast.success(isEdit ? 'Transition updated' : 'Transition created');
          onSuccess?.(saved);
          handleOpenChange(false);
        },
        onError: handleError,
      }
    );
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

            {/* Routing Predicate — collected locally, sent on submit */}
            <div className="space-y-2">
              <p className="text-sm font-medium">Routing Predicate</p>
              <p className="text-xs text-muted-foreground">
                Beat-outcome conditions — ALL must be true for this transition to fire. Submitted
                atomically with the transition fields; no partial saves.
              </p>
              {routingRows.length === 0 ? (
                <p
                  className="text-sm italic text-muted-foreground"
                  data-testid="routing-predicate-empty"
                >
                  No conditions — this transition is always eligible.
                </p>
              ) : (
                <ul className="space-y-1" data-testid="routing-predicate-list">
                  {routingRows.map((row) => (
                    <li
                      key={row.key}
                      className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                      data-testid="routing-predicate-row"
                    >
                      <span>
                        {row.beatLabel} — {row.outcome}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                        onClick={() => handleRemoveRow(row.key)}
                        aria-label="Remove routing condition"
                        data-testid="remove-routing-row-btn"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
              <AddRoutingRow
                episodeId={sourceEpisodeId}
                onAdd={handleAddRow}
                disabled={isPending}
              />
              {fieldErrors.outcomes && (
                <p className="text-xs text-destructive">
                  {Array.isArray(fieldErrors.outcomes)
                    ? fieldErrors.outcomes.join(' ')
                    : String(fieldErrors.outcomes)}
                </p>
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
      </DialogContent>
    </Dialog>
  );
}
