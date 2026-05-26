/**
 * StaffActionsCard — operator-gesture buttons for a single template.
 *
 * Embedded in MissionDetailPanel. Wraps the three D4 staff-power
 * surfaces:
 *
 * - Publish / Withdraw: PATCH access_tier between "open" and
 *   "staff_only" (gate for player-facing visibility).
 * - Copy template: POST D4.2 copy action with new_slug + new_name.
 *   Lands the copy as staff_only with all flavor flagged needs_rewrite
 *   (so the new template doesn't accidentally publish stale text).
 * - Assign: POST D4.3 staff-power assign action with a character pk.
 *   Bypasses availability filters — explicit operator gesture per the
 *   D4.3 contract, not a normal acceptance flow.
 *
 * The character picker is a numeric ObjectDB pk input rather than a
 * search-and-select dropdown — Studio v1; a richer picker lands when
 * the character-search API surfaces.
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { useAssignMission, useCopyTemplate, usePatchMissionTemplate } from '../queries';
import type { MissionTemplate } from '../types';

interface StaffActionsCardProps {
  template: MissionTemplate;
}

export function StaffActionsCard({ template }: StaffActionsCardProps) {
  const patch = usePatchMissionTemplate();
  const isOpen = template.access_tier === 'open';
  const nextTier = isOpen ? 'staff_only' : 'open';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Staff actions</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3" data-testid="staff-actions-card">
        <div className="flex items-center justify-between gap-2 rounded border p-2">
          <div>
            <div className="text-sm font-medium">Access tier</div>
            <div className="text-xs text-muted-foreground">
              Currently <Badge variant="outline">{template.access_tier}</Badge>
            </div>
          </div>
          <Button
            size="sm"
            variant={isOpen ? 'secondary' : 'default'}
            onClick={() =>
              patch.mutate({
                slug: template.slug,
                body: { access_tier: nextTier },
              })
            }
            disabled={patch.isPending}
            data-testid="access-tier-flip"
          >
            {patch.isPending ? 'Flipping…' : isOpen ? 'Withdraw' : 'Publish'}
          </Button>
        </div>
        <CopyRow template={template} />
        <AssignRow template={template} />
      </CardContent>
    </Card>
  );
}

function CopyRow({ template }: { template: MissionTemplate }) {
  const navigate = useNavigate();
  const copy = useCopyTemplate();
  const [open, setOpen] = useState(false);
  const [newSlug, setNewSlug] = useState('');
  const [newName, setNewName] = useState('');

  if (!open) {
    return (
      <div className="flex items-center justify-between gap-2 rounded border p-2">
        <div>
          <div className="text-sm font-medium">Copy template</div>
          <div className="text-xs text-muted-foreground">
            Duplicates the full graph; flavor flagged needs_rewrite.
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          Copy…
        </Button>
      </div>
    );
  }
  const onSubmit = async () => {
    if (!newSlug || !newName) return;
    const created = await copy.mutateAsync({
      slug: template.slug,
      new_slug: newSlug,
      new_name: newName,
    });
    setOpen(false);
    setNewSlug('');
    setNewName('');
    // Land on the new template's panel.
    navigate(`/staff/missions?slug=${created.slug}`);
  };
  return (
    <div className="space-y-2 rounded border p-2">
      <div className="text-sm font-medium">Copy template</div>
      <div className="grid gap-2 md:grid-cols-2">
        <div>
          <Label htmlFor="copy-new-slug">New slug</Label>
          <Input
            id="copy-new-slug"
            value={newSlug}
            onChange={(e) => setNewSlug(e.target.value)}
            placeholder="urlsafe-slug"
          />
        </div>
        <div>
          <Label htmlFor="copy-new-name">New name</Label>
          <Input id="copy-new-name" value={newName} onChange={(e) => setNewName(e.target.value)} />
        </div>
      </div>
      {copy.error ? (
        <div className="text-xs text-destructive">{String(copy.error.message)}</div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSubmit} disabled={!newSlug || !newName || copy.isPending}>
          {copy.isPending ? 'Copying…' : 'Copy'}
        </Button>
      </div>
    </div>
  );
}

function AssignRow({ template }: { template: MissionTemplate }) {
  const assign = useAssignMission();
  const [open, setOpen] = useState(false);
  const [characterPk, setCharacterPk] = useState('');
  const [feedback, setFeedback] = useState<string | null>(null);

  if (!open) {
    return (
      <div className="flex items-center justify-between gap-2 rounded border p-2">
        <div>
          <div className="text-sm font-medium">Assign to character</div>
          <div className="text-xs text-muted-foreground">
            Bypasses availability filters. Operator gesture.
          </div>
        </div>
        <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
          Assign…
        </Button>
      </div>
    );
  }
  const onSubmit = async () => {
    const pk = Number(characterPk);
    if (!pk) return;
    setFeedback(null);
    try {
      const instance = await assign.mutateAsync({ slug: template.slug, character: pk });
      setFeedback(`Created instance #${instance.id}.`);
      setCharacterPk('');
    } catch (e) {
      setFeedback(`Error: ${String((e as Error).message)}`);
    }
  };
  return (
    <div className="space-y-2 rounded border p-2">
      <div className="text-sm font-medium">Assign to character</div>
      <Label htmlFor="assign-character-pk">Character ObjectDB pk</Label>
      <Input
        id="assign-character-pk"
        type="number"
        value={characterPk}
        onChange={(e) => setCharacterPk(e.target.value)}
        placeholder="e.g. 42"
      />
      {feedback ? (
        <div
          className={
            feedback.startsWith('Error') ? 'text-xs text-destructive' : 'text-xs text-primary'
          }
          data-testid="assign-feedback"
        >
          {feedback}
        </div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
          Close
        </Button>
        <Button size="sm" onClick={onSubmit} disabled={!characterPk || assign.isPending}>
          {assign.isPending ? 'Assigning…' : 'Assign'}
        </Button>
      </div>
    </div>
  );
}
