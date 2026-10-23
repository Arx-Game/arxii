/**
 * Route editor for the option page (#4558). Each route of an option is an
 * editable row (tier, destination, random set, outcome text, beat outcome)
 * with Save and Delete; the server's plain refusal shows inline on the row.
 * Destinations and tiers are shown by name, never by id.
 */

import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

import { useCreateMissionRoute, useDeleteMissionRoute, usePatchMissionRoute } from '../queries';
import type { MissionNode, MissionOption, MissionOptionRoute, OutcomeTier } from '../types';

const NONE = 'none';
const ENDS = 'ends';
const DERIVE = 'derive';

type BeatOutcome = '' | 'success' | 'failure';

function errorText(e: unknown, fallback: string): string {
  return e instanceof Error ? e.message : fallback;
}

interface RouteDraft {
  tier: string;
  target: string;
  random: boolean;
  text: string;
  beat: string;
}

function draftFromRoute(r: MissionOptionRoute): RouteDraft {
  return {
    tier: r.outcome_tier == null ? NONE : String(r.outcome_tier),
    target: r.target_node == null ? ENDS : String(r.target_node),
    random: r.is_random_set ?? false,
    text: r.outcome_text ?? '',
    beat: r.beat_outcome ? r.beat_outcome : DERIVE,
  };
}

function sameDraft(a: RouteDraft, b: RouteDraft): boolean {
  return (
    a.tier === b.tier &&
    a.target === b.target &&
    a.random === b.random &&
    a.text === b.text &&
    a.beat === b.beat
  );
}

interface RouteRowProps {
  route: MissionOptionRoute;
  tiers: OutcomeTier[];
  nodes: MissionNode[];
}

function RouteRow({ route, tiers, nodes }: RouteRowProps) {
  const saved = draftFromRoute(route);
  const [draft, setDraft] = useState<RouteDraft>(saved);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const patch = usePatchMissionRoute();
  const del = useDeleteMissionRoute();
  const dirty = !sameDraft(draft, saved);
  const toEnd = draft.target === ENDS && !draft.random;
  const rowId = `route-${route.id}`;

  const onSave = async () => {
    setError(null);
    const beat = toEnd && draft.beat !== DERIVE ? (draft.beat as BeatOutcome) : '';
    try {
      await patch.mutateAsync({
        id: route.id,
        body: {
          outcome_tier: draft.tier === NONE ? null : Number(draft.tier),
          target_node: draft.target === ENDS || draft.random ? null : Number(draft.target),
          is_random_set: draft.random,
          outcome_text: draft.text,
          beat_outcome: beat,
        },
      });
    } catch (e) {
      setError(errorText(e, 'Failed to save route'));
    }
  };

  const onDelete = async () => {
    try {
      await del.mutateAsync(route.id);
      setConfirmDelete(false);
    } catch (e) {
      setError(errorText(e, 'Failed to delete route'));
      setConfirmDelete(false);
    }
  };

  return (
    <div className="space-y-3 rounded border p-3" data-testid="route-row">
      <div className="grid gap-3 md:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor={`${rowId}-tier`}>Outcome tier</Label>
          <Select value={draft.tier} onValueChange={(v) => setDraft({ ...draft, tier: v })}>
            <SelectTrigger id={`${rowId}-tier`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>None (branch)</SelectItem>
              {tiers.map((t) => (
                <SelectItem key={t.id} value={String(t.id)}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor={`${rowId}-target`}>Leads to</Label>
          <Select value={draft.target} onValueChange={(v) => setDraft({ ...draft, target: v })}>
            <SelectTrigger id={`${rowId}-target`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ENDS}>Mission ends</SelectItem>
              {nodes.map((n) => (
                <SelectItem key={n.id} value={String(n.id)}>
                  {n.key}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex items-center gap-2">
        <Switch
          id={`${rowId}-random`}
          checked={draft.random}
          onCheckedChange={(v) => setDraft({ ...draft, random: v })}
        />
        <Label htmlFor={`${rowId}-random`}>Random set</Label>
        {route.outcome_text_needs_rewrite ? <Badge variant="secondary">needs rewrite</Badge> : null}
      </div>
      <div className="space-y-1">
        <Label htmlFor={`${rowId}-text`}>Outcome text</Label>
        <Textarea
          id={`${rowId}-text`}
          rows={2}
          value={draft.text}
          onChange={(e) => setDraft({ ...draft, text: e.target.value })}
        />
      </div>
      {toEnd ? (
        <div className="space-y-1">
          <Label htmlFor={`${rowId}-beat`}>Beat outcome</Label>
          <Select value={draft.beat} onValueChange={(v) => setDraft({ ...draft, beat: v })}>
            <SelectTrigger id={`${rowId}-beat`}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={DERIVE}>Work it out from the tier</SelectItem>
              <SelectItem value="success">Success</SelectItem>
              <SelectItem value="failure">Failure</SelectItem>
            </SelectContent>
          </Select>
        </div>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            setError(null);
            setConfirmDelete(true);
          }}
        >
          Delete route
        </Button>
        <Button type="button" onClick={onSave} disabled={!dirty || patch.isPending}>
          {patch.isPending ? 'Saving…' : 'Save route'}
        </Button>
      </div>
      <Dialog open={confirmDelete} onOpenChange={setConfirmDelete}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete route</DialogTitle>
            <DialogDescription>Delete this route from the option?</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setConfirmDelete(false)}>
              Cancel
            </Button>
            <Button type="button" variant="destructive" onClick={onDelete} disabled={del.isPending}>
              Delete route
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

interface RouteEditorProps {
  option: MissionOption;
  routes: MissionOptionRoute[];
  /** Every node of the mission, this option's own node included. */
  nodes: MissionNode[];
  tiers: OutcomeTier[];
  /** Tier names the graph check says this option has no route for. */
  missingTierNames: string[];
}

export function RouteEditor({ option, routes, nodes, tiers, missingTierNames }: RouteEditorProps) {
  const [error, setError] = useState<string | null>(null);
  const create = useCreateMissionRoute();
  const orderedTiers = [...tiers].sort((a, b) => a.success_level - b.success_level);
  const tierless = option.option_kind === 'branch' || option.option_kind === 'external_act';
  const canAdd = !(tierless && routes.length > 0);

  const onAdd = async () => {
    setError(null);
    const used = new Set(routes.map((r) => r.outcome_tier));
    const tier = tierless ? null : (orderedTiers.find((t) => !used.has(t.id)) ?? orderedTiers[0]);
    try {
      await create.mutateAsync({
        option: option.id,
        outcome_tier: tier ? tier.id : null,
        target_node: null,
      });
    } catch (e) {
      setError(errorText(e, 'Failed to add route'));
    }
  };

  const onAddMissing = async () => {
    setError(null);
    try {
      for (const name of missingTierNames) {
        const tier = tiers.find((t) => t.name === name);
        if (!tier) continue;
        await create.mutateAsync({ option: option.id, outcome_tier: tier.id, target_node: null });
      }
    } catch (e) {
      setError(errorText(e, 'Failed to add the missing tiers'));
    }
  };

  return (
    <div className="space-y-3" data-testid="option-routes-list">
      {routes.length === 0 ? (
        <div className="text-sm text-muted-foreground">
          {tierless ? 'No routes, so this option ends the mission.' : 'No routes yet.'}
        </div>
      ) : (
        routes.map((r) => (
          <RouteRow
            key={`${r.id}:${r.outcome_tier}:${r.target_node}:${r.is_random_set}:${r.outcome_text}:${r.beat_outcome}`}
            route={r}
            tiers={orderedTiers}
            nodes={nodes}
          />
        ))
      )}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
      <div className="flex flex-wrap gap-2">
        {canAdd ? (
          <Button type="button" variant="outline" onClick={onAdd} disabled={create.isPending}>
            Add route
          </Button>
        ) : null}
        {missingTierNames.length > 0 ? (
          <Button type="button" onClick={onAddMissing} disabled={create.isPending}>
            Add the missing tiers
          </Button>
        ) : null}
      </div>
    </div>
  );
}
