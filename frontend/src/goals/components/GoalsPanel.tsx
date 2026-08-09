/**
 * GoalsPanel (#3045) — the goal-log affordance.
 *
 * Before this, `GET /api/goals/my-goals/` and `POST /api/goals/journals/`
 * (real weekly-capped XP since #3004) had zero frontend callers — no "current
 * goals" display existed anywhere outside the one-time character-creation
 * allocator (`FinalTouchesStage`). Mounted on `XpKudosPage` alongside
 * `RandomScenePanel` — an earn surface, not a spend one (#3045 decision 1).
 *
 * Character resolution mirrors `GMAdjudicationPanel`: the account's currently
 * active/puppeted character (not any specific viewed sheet), since this page
 * is account-level, and the backend resolves via the `X-Character-ID` header.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCreateGoalJournalMutation, useGoalDomainsQuery, useMyGoalsQuery } from '../queries';

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50';

function LogProgressDialog({ characterId }: { characterId: number }) {
  const [open, setOpen] = useState(false);
  const [domainId, setDomainId] = useState<number | null>(null);
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [isPublic, setIsPublic] = useState(false);
  const { data: domains = [] } = useGoalDomainsQuery();
  const logProgress = useCreateGoalJournalMutation(characterId);

  const canSubmit = title.trim() !== '' && content.trim() !== '' && !logProgress.isPending;

  function reset() {
    setDomainId(null);
    setTitle('');
    setContent('');
    setIsPublic(false);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) reset();
  }

  function handleSubmit() {
    if (!canSubmit) return;
    logProgress.mutate(
      { domain: domainId, title: title.trim(), content: content.trim(), is_public: isPublic },
      {
        onSuccess: (entry) => {
          toast.success(
            entry.xp_awarded > 0
              ? `Logged — earned ${entry.xp_awarded} XP.`
              : 'Logged — no XP awarded (weekly cap reached).'
          );
          handleOpenChange(false);
        },
        onError: (err: unknown) =>
          toast.error(err instanceof Error ? err.message : 'Could not log goal progress.'),
      }
    );
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button size="sm" data-testid="goals-log-progress-trigger">
          Log Progress
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Log Goal Progress</DialogTitle>
          <DialogDescription>
            Writing about your progress toward a goal earns XP (weekly capped).
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="space-y-1">
            <Label htmlFor="goal-log-domain">Domain (optional)</Label>
            <select
              id="goal-log-domain"
              className={SELECT_CLASS}
              value={domainId ?? ''}
              onChange={(e) => setDomainId(e.target.value ? Number(e.target.value) : null)}
              data-testid="goals-log-domain-select"
            >
              <option value="">No specific domain</option>
              {domains.map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
          </div>
          <div className="space-y-1">
            <Label htmlFor="goal-log-title">Title</Label>
            <Input
              id="goal-log-title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              data-testid="goals-log-title-input"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="goal-log-content">What happened?</Label>
            <Textarea
              id="goal-log-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              data-testid="goals-log-content-input"
            />
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
              data-testid="goals-log-public-checkbox"
            />
            Make this entry public
          </label>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => handleOpenChange(false)}>
            Cancel
          </Button>
          <Button disabled={!canSubmit} onClick={handleSubmit} data-testid="goals-log-submit">
            {logProgress.isPending ? 'Logging…' : 'Log Progress'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function GoalsPanel() {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId =
    myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null;

  const { data, isLoading, error } = useMyGoalsQuery(characterId ?? 0);

  if (characterId === null) return null;

  const goals = data?.goals ?? [];

  return (
    <Card data-testid="goals-panel">
      <CardHeader>
        <CardTitle className="text-base">Goals</CardTitle>
        {data && <CardDescription>{data.points_remaining} points remaining</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <p className="text-sm text-muted-foreground">Loading…</p>}
        {error && <p className="text-sm text-destructive">Failed to load goals.</p>}
        {!isLoading && !error && goals.length === 0 && (
          <p className="text-sm text-muted-foreground" data-testid="goals-empty">
            No goals set yet.
          </p>
        )}
        {goals.length > 0 && (
          <ul className="space-y-1">
            {goals.map((g) => (
              <li key={g.id} className="flex items-center justify-between text-sm">
                <span>{g.domain_name}</span>
                <Badge variant="outline">{g.points} pts</Badge>
              </li>
            ))}
          </ul>
        )}
        <LogProgressDialog characterId={characterId} />
      </CardContent>
    </Card>
  );
}
