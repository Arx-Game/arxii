/**
 * GiverEditorPage — edit one MissionGiver + manage its offerings.
 *
 * Routes: /staff/missions/givers/:slug. The page wires three D3
 * surfaces:
 *
 * - MissionGiverViewSet (PATCH/DELETE on the giver row itself)
 * - MissionGiverOfferingViewSet (list + create + patch + delete)
 *
 * Offerings reuse E4's PredicateBuilder for the per-link
 * `requirements_override` tree (AND-composed with the template's
 * own availability_rule at draw time — see Phase D wiring note in
 * the MissionGiverOffering schema).
 *
 * "target" is the ObjectDB pk the giver is bound to; clean() on the
 * model validates typeclass against giver_kind, surfaced as 400 from
 * the serializer. The page surfaces the JSON body of any 400 in a
 * plain error row — fancier per-field rendering is a follow-up.
 */

import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';

import {
  coercePredicate,
  PredicateBuilder,
  validatePredicate,
  type PredicateNode,
} from '../components/PredicateBuilder';
import { ServerChangedBanner } from '../components/ServerChangedBanner';
import { StudioBreadcrumb } from '../components/StudioBreadcrumb';
import { type GiverKind, GIVER_KINDS } from '../constants';
import { useServerDraft } from '../hooks/useServerDraft';
import {
  useCreateGiverOffering,
  useDeleteGiverOffering,
  useDeleteMissionGiver,
  useGiverOfferings,
  useMissionGiver,
  useMissionTemplates,
  usePatchGiverOffering,
  usePatchMissionGiver,
  usePredicateLeaves,
} from '../queries';
import type { MissionGiver, MissionGiverOffering } from '../types';

export function GiverEditorPage() {
  const { id: idStr } = useParams<{ id: string }>();
  const giverId = idStr ? Number(idStr) : undefined;
  const { data: giver, isLoading } = useMissionGiver(giverId);

  if (!giverId) {
    return <div className="p-6 text-destructive">Missing id in URL.</div>;
  }

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      <StudioBreadcrumb
        crumbs={[
          { label: 'Missions', to: '/staff/missions' },
          { label: 'Givers', to: '/staff/missions/givers' },
          { label: giver?.name ?? (giverId ? `#${giverId}` : '…') },
        ]}
      />
      {isLoading || !giver ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <GiverFields giver={giver} />
          <OfferingsSection giverId={giver.id} />
        </>
      )}
    </div>
  );
}

function GiverFields({ giver }: { giver: MissionGiver }) {
  const navigate = useNavigate();
  const patch = usePatchMissionGiver();
  const del = useDeleteMissionGiver();
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(giver, (g) => ({
    name: g.name,
    giver_kind: (g.giver_kind ?? 'npc') as GiverKind,
    target: g.target ?? null,
    org: g.org ?? null,
    is_active: g.is_active ?? true,
  }));

  const onSave = () => patch.mutate({ id: giver.id, body: draft });

  const onDelete = async () => {
    if (!confirm(`Delete giver "${giver.name}" (slug=${giver.slug})? This cannot be undone.`)) {
      return;
    }
    await del.mutateAsync(giver.id);
    navigate('/staff/missions/givers');
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>Giver: {giver.name}</span>
          <span className="flex items-center gap-2 text-sm font-normal">
            <Badge variant="outline">slug: {giver.slug}</Badge>
            {giver.is_publishable ? (
              <Badge variant="secondary">publishable</Badge>
            ) : (
              <Badge variant="destructive">draft (no target)</Badge>
            )}
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {serverChanged ? (
          <ServerChangedBanner onPull={pullFromServer} className="md:col-span-2" />
        ) : null}
        <div className="md:col-span-2">
          <Label htmlFor="giver-name">Name</Label>
          <Input
            id="giver-name"
            value={draft.name}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="giver-kind">Kind</Label>
          <Select
            value={draft.giver_kind}
            onValueChange={(v) => setDraft({ ...draft, giver_kind: v as GiverKind })}
          >
            <SelectTrigger id="giver-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {GIVER_KINDS.map((k) => (
                <SelectItem key={k.value} value={k.value}>
                  {k.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="giver-target">
            Target ObjectDB pk
            <span className="ml-1 text-xs text-muted-foreground">(typeclass must match kind)</span>
          </Label>
          <Input
            id="giver-target"
            type="number"
            value={draft.target ?? ''}
            onChange={(e) =>
              setDraft({
                ...draft,
                target: e.target.value === '' ? null : Number(e.target.value),
              })
            }
            placeholder="unbound"
          />
        </div>
        <div>
          <Label htmlFor="giver-org">Org pk (optional)</Label>
          <Input
            id="giver-org"
            type="number"
            value={draft.org ?? ''}
            onChange={(e) =>
              setDraft({
                ...draft,
                org: e.target.value === '' ? null : Number(e.target.value),
              })
            }
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="giver-active"
            checked={draft.is_active}
            onCheckedChange={(v) => setDraft({ ...draft, is_active: v })}
          />
          <Label htmlFor="giver-active">Active</Label>
        </div>
        {patch.error ? (
          <div className="text-sm text-destructive md:col-span-2" data-testid="giver-save-error">
            {String(patch.error.message)}
          </div>
        ) : null}
        <div className="flex items-center justify-between md:col-span-2">
          <Button variant="destructive" onClick={onDelete} disabled={del.isPending}>
            {del.isPending ? 'Deleting…' : 'Delete giver'}
          </Button>
          <Button onClick={onSave} disabled={!dirty || patch.isPending}>
            {patch.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function OfferingsSection({ giverId }: { giverId: number }) {
  const { data, isLoading } = useGiverOfferings({ giver: giverId });
  const [addOpen, setAddOpen] = useState(false);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span>Mission offerings</span>
          <Button size="sm" onClick={() => setAddOpen((v) => !v)}>
            {addOpen ? 'Cancel add' : '+ Add offering'}
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3" data-testid="offerings-list">
        {addOpen ? <NewOfferingRow giverId={giverId} onDone={() => setAddOpen(false)} /> : null}
        {isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (data?.results?.length ?? 0) === 0 ? (
          <div className="text-sm text-muted-foreground">No offerings yet.</div>
        ) : (
          (data?.results ?? []).map((o) => <OfferingRow key={o.id} offering={o} />)
        )}
      </CardContent>
    </Card>
  );
}

function OfferingRow({ offering }: { offering: MissionGiverOffering }) {
  const patch = usePatchGiverOffering();
  const del = useDeleteGiverOffering();
  const leaves = usePredicateLeaves();
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(
    offering,
    (o) => ({
      weight_override: o.weight_override ?? null,
      requirements_override: (o.requirements_override ?? {}) as PredicateNode,
    })
  );
  const ruleErrors = validatePredicate(draft.requirements_override, leaves.data ?? []);
  const ruleValid = ruleErrors.length === 0;

  const onDelete = () => {
    if (!confirm(`Remove offering for template #${offering.template}? This cannot be undone.`)) {
      return;
    }
    del.mutate(offering.id);
  };

  const onSave = () => {
    patch.mutate({
      id: offering.id,
      body: {
        ...draft,
        requirements_override: coercePredicate(draft.requirements_override, leaves.data ?? []),
      },
    });
  };

  return (
    <div
      className="space-y-3 rounded border p-3"
      data-testid="offering-row"
      data-template={offering.template}
    >
      {serverChanged ? <ServerChangedBanner onPull={pullFromServer} /> : null}
      <div className="flex items-center justify-between gap-2">
        <span className="text-sm font-medium">Template #{offering.template}</span>
        <Button size="sm" variant="ghost" onClick={onDelete} disabled={del.isPending}>
          Remove
        </Button>
      </div>
      <div>
        <Label htmlFor={`weight-${offering.id}`}>
          Weight override
          <span className="ml-1 text-xs text-muted-foreground">
            (blank = use template.base_weight; 0 rejected)
          </span>
        </Label>
        <Input
          id={`weight-${offering.id}`}
          type="number"
          value={draft.weight_override ?? ''}
          onChange={(e) =>
            setDraft({
              ...draft,
              weight_override: e.target.value === '' ? null : Number(e.target.value),
            })
          }
        />
      </div>
      <div>
        <PredicateBuilder
          label="Requirements override (AND-composed with template rule)"
          value={draft.requirements_override}
          onChange={(next) => setDraft({ ...draft, requirements_override: next })}
        />
      </div>
      {!ruleValid && dirty ? (
        <div className="rounded border border-destructive/60 bg-destructive/10 px-2 py-1 text-xs text-destructive">
          <div className="font-medium">Requirements override is not safe to save:</div>
          <ul className="list-inside list-disc">
            {ruleErrors.map((err) => (
              <li key={err}>{err}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {patch.error ? (
        <div className="text-sm text-destructive">{String(patch.error.message)}</div>
      ) : null}
      <div className="flex justify-end">
        <Button size="sm" onClick={onSave} disabled={!dirty || !ruleValid || patch.isPending}>
          {patch.isPending ? 'Saving…' : 'Save'}
        </Button>
      </div>
    </div>
  );
}

function NewOfferingRow({ giverId, onDone }: { giverId: number; onDone: () => void }) {
  const create = useCreateGiverOffering();
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [search, setSearch] = useState('');
  const { data: templates } = useMissionTemplates({ name: search || undefined });

  const onSubmit = async () => {
    if (templateId === null) return;
    await create.mutateAsync({ giver: giverId, template: templateId });
    onDone();
  };

  return (
    <div className="space-y-2 rounded border-l-2 border-primary/40 bg-muted/30 p-3">
      <div className="grid gap-2 md:grid-cols-2">
        <div>
          <Label htmlFor="offering-template-search">Template (search by name)</Label>
          <Input
            id="offering-template-search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="search..."
          />
        </div>
        <div>
          <Label htmlFor="offering-template-pick">Match</Label>
          <Select
            value={templateId !== null ? String(templateId) : ''}
            onValueChange={(v) => setTemplateId(v ? Number(v) : null)}
          >
            <SelectTrigger id="offering-template-pick">
              <SelectValue placeholder="Pick…" />
            </SelectTrigger>
            <SelectContent>
              {(templates?.results ?? []).map((t) => (
                <SelectItem key={t.id} value={String(t.id)}>
                  {t.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      {create.error ? (
        <div className="text-sm text-destructive">{String(create.error.message)}</div>
      ) : null}
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onDone}>
          Cancel
        </Button>
        <Button size="sm" onClick={onSubmit} disabled={templateId === null || create.isPending}>
          {create.isPending ? 'Adding…' : 'Add'}
        </Button>
      </div>
      <Link
        to="/staff/missions"
        target="_blank"
        className="text-xs text-muted-foreground hover:underline"
      >
        (open templates browser ↗)
      </Link>
    </div>
  );
}
