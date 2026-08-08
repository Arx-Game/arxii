/**
 * TrainingCard (#3045) — deliberate skill training allocation.
 *
 * Thin web face over `ManageTrainingAction` (`world.skills.views
 * .TrainingAllocationViewSet`) — the same seam telnet's `training` command
 * dispatches. Does not preempt the NPC-trainer check-composition design
 * question (#2740/#2741) — a mentor here is just an optional Persona pick,
 * exactly what `mentor_persona_id` already accepts server-side; no eligible-
 * mentor filtering exists (or is invented here), so the picker is the same
 * generic persona search other invite/mentor pickers use.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import {
  useCreateTrainingAllocationMutation,
  useDeleteTrainingAllocationMutation,
  useSkillsCatalogQuery,
  useTrainingAllocationsQuery,
  useUpdateTrainingAllocationMutation,
} from '@/skills/queries';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function MentorPicker({
  onSelect,
  selectedName,
}: {
  onSelect: (personaId: number | null, name: string) => void;
  selectedName: string;
}) {
  const [query, setQuery] = useState(selectedName);
  const { results, isFetching } = usePersonaSearch(query);
  const showResults = results.length > 0 && query !== selectedName;

  return (
    <div className="relative">
      <Input
        placeholder="Mentor (optional)…"
        value={query}
        onChange={(e) => {
          setQuery(e.target.value);
          onSelect(null, '');
        }}
        data-testid="training-mentor-search"
      />
      {isFetching && (
        <span className="absolute right-2 top-2 text-xs text-muted-foreground">Searching…</span>
      )}
      {showResults && (
        <ul className="absolute z-50 mt-1 max-h-40 w-full overflow-auto rounded-md border bg-popover shadow-lg">
          {results.map((p) => (
            <li key={p.id}>
              <button
                type="button"
                className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                onClick={() => {
                  setQuery(p.name);
                  onSelect(p.id, p.name);
                }}
              >
                {p.name}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AddAllocationForm() {
  const { data: skills = [] } = useSkillsCatalogQuery();
  const [skillId, setSkillId] = useState<number | null>(null);
  const [apAmount, setApAmount] = useState('1');
  const [mentorId, setMentorId] = useState<number | null>(null);
  const [mentorName, setMentorName] = useState('');
  const create = useCreateTrainingAllocationMutation();

  const parsedAp = parseInt(apAmount, 10);
  const canSubmit = skillId !== null && !isNaN(parsedAp) && parsedAp >= 1 && !create.isPending;

  function handleSubmit() {
    if (!canSubmit || skillId === null) return;
    create.mutate(
      {
        skill_id: skillId,
        ap_amount: parsedAp,
        mentor_persona_id: mentorId ?? undefined,
      },
      {
        onSuccess: () => {
          toast.success('Training allocated.');
          setSkillId(null);
          setApAmount('1');
          setMentorId(null);
          setMentorName('');
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not allocate training.'),
      }
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-dashed p-3" data-testid="training-add-form">
      <div className="grid gap-2 sm:grid-cols-3">
        <div className="space-y-1">
          <Label htmlFor="training-add-skill">Skill</Label>
          <select
            id="training-add-skill"
            className={SELECT_CLASS}
            value={skillId ?? ''}
            onChange={(e) => setSkillId(e.target.value ? Number(e.target.value) : null)}
            data-testid="training-skill-select"
          >
            <option value="">Select a skill…</option>
            {skills.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="training-add-ap">AP</Label>
          <Input
            id="training-add-ap"
            type="number"
            min={1}
            value={apAmount}
            onChange={(e) => setApAmount(e.target.value)}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="training-add-mentor">Mentor</Label>
          <MentorPicker
            onSelect={(id, name) => {
              setMentorId(id);
              setMentorName(name);
            }}
            selectedName={mentorName}
          />
        </div>
      </div>
      <Button
        size="sm"
        disabled={!canSubmit}
        onClick={handleSubmit}
        data-testid="training-add-submit"
      >
        {create.isPending ? 'Allocating…' : 'Allocate Training'}
      </Button>
    </div>
  );
}

export function TrainingCard() {
  const { data, isLoading, error } = useTrainingAllocationsQuery();
  const update = useUpdateTrainingAllocationMutation();
  const remove = useDeleteTrainingAllocationMutation();

  const allocations = data?.allocations ?? [];
  const remaining = data?.remaining_weekly_budget;

  function handleRemove(id: number) {
    remove.mutate(id, {
      onSuccess: () => toast.success('Training allocation removed.'),
      onError: (err: unknown) =>
        toast.error(err instanceof Error ? err.message : 'Could not remove the allocation.'),
    });
  }

  function handleApChange(id: number, ap: number) {
    if (isNaN(ap) || ap < 1) return;
    update.mutate(
      { id, body: { ap_amount: ap } },
      {
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not update the allocation.'),
      }
    );
  }

  return (
    <Card data-testid="training-card">
      <CardHeader>
        <CardTitle className="text-base">Training</CardTitle>
        {remaining !== undefined && (
          <CardDescription>{remaining} AP remaining this week</CardDescription>
        )}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load training allocations.</p>}
        {!isLoading && !error && allocations.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="training-empty">
            No training allocated this week.
          </p>
        )}
        {allocations.map((allocation) => (
          <div
            key={allocation.id}
            className="flex items-center justify-between gap-3 rounded-lg border p-3"
            data-testid="training-allocation-row"
          >
            <div className="min-w-0">
              <div className="font-medium">
                {allocation.skill?.name ?? allocation.specialization?.name}
              </div>
              <div className="text-sm text-muted-foreground">
                {allocation.mentor ? (
                  <span>Mentor: {allocation.mentor.name}</span>
                ) : (
                  <Badge variant="outline">Self-study</Badge>
                )}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <Input
                type="number"
                min={1}
                className="w-16"
                defaultValue={allocation.ap_amount}
                onBlur={(e) => handleApChange(allocation.id, parseInt(e.target.value, 10))}
                data-testid={`training-ap-input-${allocation.id}`}
              />
              <Button
                variant="outline"
                size="sm"
                disabled={remove.isPending && remove.variables === allocation.id}
                onClick={() => handleRemove(allocation.id)}
                data-testid={`training-remove-${allocation.id}`}
              >
                Remove
              </Button>
            </div>
          </div>
        ))}
        <AddAllocationForm />
      </CardContent>
    </Card>
  );
}
