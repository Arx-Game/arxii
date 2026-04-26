/**
 * ProgressionRequirementsEditor — embedded in EpisodeFormDialog.
 *
 * Lists EpisodeProgressionRequirement rows for an episode and lets the author
 * add (beat + required_outcome) pairs or remove existing ones.
 *
 * Approach A (multi-roundtrip): after the parent episode save, row operations
 * call POST /api/episode-progression-requirements/ or DELETE per row individually.
 * No backend transaction endpoint exists.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Trash2, Plus } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import {
  useProgressionRequirements,
  useCreateProgressionRequirement,
  useDeleteProgressionRequirement,
  useBeatList,
} from '../queries';
import type { EpisodeProgressionRequirement } from '../types';
import { Combobox } from '@/components/ui/combobox';

// ---------------------------------------------------------------------------
// Beat outcome options
// ---------------------------------------------------------------------------

const OUTCOME_OPTIONS = [
  { value: 'success', label: 'Success' },
  { value: 'failure', label: 'Failure' },
  { value: 'expired', label: 'Expired' },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ProgressionRequirementsEditorProps {
  episodeId: number;
}

// ---------------------------------------------------------------------------
// Row editor for adding a new requirement
// ---------------------------------------------------------------------------

interface AddRowProps {
  episodeId: number;
  onAdded: () => void;
}

function AddRequirementRow({ episodeId, onAdded }: AddRowProps) {
  const [beatId, setBeatId] = useState('');
  const [outcome, setOutcome] = useState('success');
  const [adding, setAdding] = useState(false);

  const createMutation = useCreateProgressionRequirement();

  // Load beats for this episode
  const { data: beatsData } = useBeatList({ episode: episodeId, page_size: 100 });
  const beatOptions =
    beatsData?.results.map((b) => ({
      value: String(b.id),
      label: `#${b.id}: ${b.internal_description?.slice(0, 50) ?? '(no description)'}`,
    })) ?? [];

  function handleAdd() {
    if (!beatId) return;
    const data: Omit<EpisodeProgressionRequirement, 'id'> = {
      episode: episodeId,
      beat: Number(beatId),
      required_outcome: outcome as EpisodeProgressionRequirement['required_outcome'],
    };
    createMutation.mutate(data, {
      onSuccess: () => {
        setBeatId('');
        setOutcome('success');
        setAdding(false);
        onAdded();
      },
      onError: () => toast.error('Failed to add requirement'),
    });
  }

  if (!adding) {
    return (
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="mt-2 gap-1"
        onClick={() => setAdding(true)}
        data-testid="add-requirement-btn"
      >
        <Plus className="h-3 w-3" />
        Add Requirement
      </Button>
    );
  }

  return (
    <div
      className="mt-2 flex flex-col gap-2 rounded-md border p-3"
      data-testid="add-requirement-form"
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
          onClick={handleAdd}
          disabled={!beatId || createMutation.isPending}
          data-testid="confirm-add-requirement"
        >
          {createMutation.isPending ? 'Adding…' : 'Add'}
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={() => setAdding(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main editor
// ---------------------------------------------------------------------------

export function ProgressionRequirementsEditor({ episodeId }: ProgressionRequirementsEditorProps) {
  const { data, refetch } = useProgressionRequirements({ episode: episodeId });
  const deleteMutation = useDeleteProgressionRequirement();

  const requirements = data?.results ?? [];

  function handleDelete(req: EpisodeProgressionRequirement) {
    deleteMutation.mutate(
      { id: req.id, episodeId },
      {
        onSuccess: () => toast.success('Requirement removed'),
        onError: () => toast.error('Failed to remove requirement'),
      }
    );
  }

  return (
    <div className="space-y-2">
      <div>
        <p className="text-sm font-medium">Progression Requirements</p>
        <p className="text-xs text-muted-foreground">
          Beats that must reach their required outcome before any outbound transition is eligible.
        </p>
      </div>

      {requirements.length === 0 ? (
        <p
          className="text-sm italic text-muted-foreground"
          data-testid="progression-requirements-empty"
        >
          No progression requirements.
        </p>
      ) : (
        <ul className="space-y-1" data-testid="progression-requirements-list">
          {requirements.map((req) => (
            <li
              key={req.id}
              className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
              data-testid="progression-requirement-row"
            >
              <span>
                Beat #{req.beat} — {req.required_outcome ?? 'success'}
              </span>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 w-6 p-0 text-muted-foreground hover:text-destructive"
                onClick={() => handleDelete(req)}
                disabled={deleteMutation.isPending}
                aria-label="Remove requirement"
                data-testid="remove-requirement-btn"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </li>
          ))}
        </ul>
      )}

      <AddRequirementRow episodeId={episodeId} onAdded={() => void refetch()} />
    </div>
  );
}
