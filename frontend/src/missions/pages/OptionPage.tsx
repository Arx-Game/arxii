/**
 * OptionPage — edit one MissionOption, list its routes.
 *
 * Routes: /staff/missions/:slug/nodes/:nodeId/options/:optionId. PATCH
 * on save via D2's MissionOptionViewSet. Routes listed by tier with a
 * tag for is_random_set (= "random pool"); per-route candidate / reward
 * editing is a future enhancement (D2's nested CRUD endpoints exist;
 * the UI for them lands in a follow-up Studio iteration).
 *
 * The visibility_rule predicate tree is rendered raw here (JSON);
 * PredicateBuilder integration lands in E4.
 */

import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';

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
import { Textarea } from '@/components/ui/textarea';

import { PredicateBuilder, type PredicateNode } from '../components/PredicateBuilder';
import { StudioBreadcrumb } from '../components/StudioBreadcrumb';
import { getMissionOption, patchMissionOption } from '../api';
import { missionKeys, useMissionRoutes, useMissionTemplate } from '../queries';
import type { MissionOption } from '../types';
import { useMutation } from '@tanstack/react-query';

const KINDS = ['branch', 'check'] as const;
const SOURCES = ['authored', 'challenge'] as const;

export function OptionPage() {
  const { slug, nodeId, optionId } = useParams<{
    slug: string;
    nodeId: string;
    optionId: string;
  }>();
  const numericOptionId = Number(optionId);
  const numericNodeId = Number(nodeId);
  const { data: template } = useMissionTemplate(slug);
  const { data: option, isLoading } = useOption(numericOptionId);
  const { data: routesPage } = useMissionRoutes({ option: numericOptionId });

  if (Number.isNaN(numericOptionId)) {
    return <div className="p-6 text-destructive">Bad option id.</div>;
  }

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      <StudioBreadcrumb
        crumbs={[
          { label: 'Missions', to: '/staff/missions' },
          {
            label: template?.name ?? slug ?? '…',
            to: `/staff/missions?slug=${slug ?? ''}`,
          },
          {
            label: 'Node',
            to: `/staff/missions/${slug}/nodes/${numericNodeId}`,
          },
          { label: option ? `Option #${option.order}` : '…' },
        ]}
      />
      {isLoading || !option ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <OptionEditor option={option} />
      )}
      <Card>
        <CardHeader>
          <CardTitle>Routes</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1" data-testid="option-routes-list">
          {routesPage && routesPage.results.length > 0 ? (
            routesPage.results.map((r) => (
              <div
                key={r.id}
                className="flex items-center justify-between gap-2 rounded border px-2 py-1 text-sm"
              >
                <span>
                  Outcome {r.outcome_tier ?? '<branch>'} → node {r.target_node ?? '<none>'}
                </span>
                <span className="flex gap-1 text-xs">
                  {r.is_random_set ? <Badge variant="outline">random pool</Badge> : null}
                  {r.outcome_text_needs_rewrite ? (
                    <Badge variant="secondary">needs rewrite</Badge>
                  ) : null}
                </span>
              </div>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">No routes yet.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function useOption(id: number) {
  return useQuery({
    queryKey: [...missionKeys.options(), 'detail', id],
    queryFn: () => getMissionOption(id),
    enabled: !Number.isNaN(id) && id > 0,
    throwOnError: true,
  });
}

function OptionEditor({ option }: { option: MissionOption }) {
  const qc = useQueryClient();
  const [draft, setDraft] = useState({
    order: option.order,
    option_kind: option.option_kind,
    source_kind: option.source_kind,
    authored_ic_framing: option.authored_ic_framing ?? '',
    authored_ic_framing_needs_rewrite: option.authored_ic_framing_needs_rewrite ?? false,
    authored_base_risk: option.authored_base_risk ?? 0,
    visibility_rule: (option.visibility_rule ?? {}) as PredicateNode,
  });

  const mutation = useMutation({
    mutationFn: () => patchMissionOption(option.id, draft),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...missionKeys.options(), 'detail', option.id],
      });
      qc.invalidateQueries({ queryKey: missionKeys.options() });
    },
  });

  const dirty = useMemo(
    () =>
      draft.order !== option.order ||
      draft.option_kind !== option.option_kind ||
      draft.source_kind !== option.source_kind ||
      draft.authored_ic_framing !== (option.authored_ic_framing ?? '') ||
      draft.authored_ic_framing_needs_rewrite !==
        (option.authored_ic_framing_needs_rewrite ?? false) ||
      draft.authored_base_risk !== (option.authored_base_risk ?? 0) ||
      JSON.stringify(draft.visibility_rule) !== JSON.stringify(option.visibility_rule ?? {}),
    [draft, option]
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>Option settings</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        <div>
          <Label htmlFor="opt-order">Order</Label>
          <Input
            id="opt-order"
            type="number"
            value={draft.order}
            onChange={(e) => setDraft({ ...draft, order: Number(e.target.value || 0) })}
          />
        </div>
        <div>
          <Label htmlFor="opt-kind">Kind</Label>
          <Select
            value={draft.option_kind}
            onValueChange={(v) => setDraft({ ...draft, option_kind: v as (typeof KINDS)[number] })}
          >
            <SelectTrigger id="opt-kind">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {KINDS.map((k) => (
                <SelectItem key={k} value={k}>
                  {k}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="opt-source">Source</Label>
          <Select
            value={draft.source_kind}
            onValueChange={(v) =>
              setDraft({ ...draft, source_kind: v as (typeof SOURCES)[number] })
            }
          >
            <SelectTrigger id="opt-source">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {SOURCES.map((s) => (
                <SelectItem key={s} value={s}>
                  {s}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="opt-risk">Base risk</Label>
          <Input
            id="opt-risk"
            type="number"
            value={draft.authored_base_risk}
            onChange={(e) =>
              setDraft({
                ...draft,
                authored_base_risk: Number(e.target.value || 0),
              })
            }
          />
        </div>
        <div className="md:col-span-2">
          <Label htmlFor="opt-framing">IC framing</Label>
          <Textarea
            id="opt-framing"
            value={draft.authored_ic_framing}
            onChange={(e) => setDraft({ ...draft, authored_ic_framing: e.target.value })}
            rows={3}
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="opt-needs-rewrite"
            checked={draft.authored_ic_framing_needs_rewrite}
            onCheckedChange={(v) => setDraft({ ...draft, authored_ic_framing_needs_rewrite: v })}
          />
          <Label htmlFor="opt-needs-rewrite">Framing needs rewrite</Label>
        </div>
        <div className="border-t pt-3 md:col-span-2">
          <PredicateBuilder
            label="Visibility rule"
            value={draft.visibility_rule}
            onChange={(next) => setDraft({ ...draft, visibility_rule: next })}
          />
        </div>
        <div className="flex items-center justify-end gap-2 md:col-span-2">
          <Button onClick={() => mutation.mutate()} disabled={!dirty || mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
