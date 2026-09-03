/**
 * OptionPage — edit one MissionOption, list its routes.
 *
 * Mounted twice: /staff/missions/:id/nodes/:nodeId/options/:optionId
 * (StaffRoute) and /stories/scenarios/:id/nodes/:nodeId/options/:optionId
 * (GMRoute, #3565) - studioPaths derives which mount is live from the
 * current URL. PATCH on save via D2's MissionOptionViewSet. Routes
 * listed by tier with a tag for is_random_set (= "random pool");
 * per-route candidate / reward editing is a future enhancement (D2's
 * nested CRUD endpoints exist; the UI for them lands in a follow-up
 * Studio iteration).
 *
 * ENCOUNTER options (#3565) author a risk level + opponent lines:
 * check-only fields (base risk) hide the same way they hide for BRANCH.
 *
 * The visibility_rule predicate tree is rendered raw here (JSON);
 * PredicateBuilder integration lands in E4.
 */

import { useLocation, useNavigate, useParams } from 'react-router-dom';
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
import { OpponentLineDraft, OpponentLinesEditor } from '@/stories/components/OpponentLinesEditor';
import { useCheckTypeCatalog } from '@/gm-adjudication/queries';

import {
  coercePredicate,
  PredicateBuilder,
  validatePredicate,
  type PredicateNode,
} from '../components/PredicateBuilder';
import { ServerChangedBanner } from '../components/ServerChangedBanner';
import { StudioBreadcrumb } from '../components/StudioBreadcrumb';
import { getMissionOption, patchMissionOption } from '../api';
import { useServerDraft } from '../hooks/useServerDraft';
import { missionKeys, usePredicateLeaves, useMissionRoutes, useMissionTemplate } from '../queries';
import { studioBaseFromPath, studioPaths } from '../studioPaths';
import type { MissionOption } from '../types';
import { useMutation } from '@tanstack/react-query';

const KINDS = ['branch', 'check', 'contest', 'external_act', 'encounter'] as const;
const SOURCES = ['authored', 'challenge'] as const;
const RISK_LEVELS = ['low', 'moderate', 'high', 'extreme', 'lethal'] as const;

function opponentLineDraftsFromOption(lines: MissionOption['opponent_lines']): OpponentLineDraft[] {
  return (lines ?? []).map((line) => ({
    id: line.id,
    creature_template: String(line.creature_template),
    count: String(line.count ?? 1),
    position_name: line.position_name ?? '',
  }));
}

function opponentLineDraftsToPayload(
  drafts: OpponentLineDraft[]
): NonNullable<MissionOption['opponent_lines']> {
  return drafts
    .filter((d) => d.creature_template !== '')
    .map((d) => ({
      ...(d.id !== undefined ? { id: d.id } : {}),
      creature_template: Number(d.creature_template),
      count: d.count !== '' ? Number(d.count) : 1,
      position_name: d.position_name.trim(),
      order: 0,
    }));
}

export function OptionPage() {
  const {
    id: idStr,
    nodeId,
    optionId,
  } = useParams<{
    id: string;
    nodeId: string;
    optionId: string;
  }>();
  const templateId = idStr ? Number(idStr) : undefined;
  const numericOptionId = Number(optionId);
  const numericNodeId = Number(nodeId);
  const { data: template } = useMissionTemplate(templateId);
  const { data: option, isLoading, isError } = useOption(numericOptionId);
  const { data: routesPage } = useMissionRoutes({ option: numericOptionId });
  const navigate = useNavigate();
  const location = useLocation();
  const base = studioBaseFromPath(location.pathname);
  const paths = studioPaths(base, templateId ?? 0, template?.story_id);

  if (Number.isNaN(numericOptionId)) {
    return <div className="p-6 text-destructive">Bad option id.</div>;
  }

  if (isError) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <div
          className="rounded border border-destructive bg-destructive/10 p-4 text-sm"
          role="alert"
        >
          <p className="font-medium">Couldn't load this option.</p>
          <Button variant="outline" className="mt-3" onClick={() => navigate(paths.browser)}>
            ← Back to {paths.browserLabel}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      <StudioBreadcrumb
        crumbs={[
          { label: paths.browserLabel, to: paths.browser },
          {
            label: template?.name ?? (templateId ? `#${templateId}` : '…'),
            to: paths.canvas,
          },
          {
            label: 'Node',
            to:
              templateId !== undefined && Number.isFinite(templateId)
                ? paths.node(numericNodeId)
                : paths.browser,
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
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

function OptionEditor({ option }: { option: MissionOption }) {
  const qc = useQueryClient();
  const leaves = usePredicateLeaves();
  const { data: checkTypes = [] } = useCheckTypeCatalog('', true);
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(option, (o) => ({
    order: o.order,
    option_kind: o.option_kind,
    source_kind: o.source_kind,
    authored_ic_framing: o.authored_ic_framing ?? '',
    authored_ic_framing_needs_rewrite: o.authored_ic_framing_needs_rewrite ?? false,
    authored_base_risk: o.authored_base_risk ?? 0,
    authored_check_type: o.authored_check_type ?? null,
    visibility_rule: (o.visibility_rule ?? {}) as PredicateNode,
    encounter_risk_level: o.encounter_risk_level ?? '',
    opponent_lines: opponentLineDraftsFromOption(o.opponent_lines),
    opposition_sheet: o.opposition_sheet ?? null,
    opposition_check_type: o.opposition_check_type ?? null,
  }));

  // Validate the predicate tree before save — blocks empty leaves, missing
  // required params, and malformed NOT groups so we don't ship a tree that
  // crashes _eligible_templates at evaluate time.
  const ruleErrors = validatePredicate(draft.visibility_rule, leaves.data ?? []);
  const ruleValid = ruleErrors.length === 0;

  const isEncounter = draft.option_kind === 'encounter';
  const isCheck = draft.option_kind === 'check';
  const isContest = draft.option_kind === 'contest';

  const mutation = useMutation({
    mutationFn: () =>
      patchMissionOption(option.id, {
        ...draft,
        // Coerce string-typed leaf params to int / bool / float per the
        // D5 catalog so the backend resolver gets the type it expects.
        visibility_rule: coercePredicate(draft.visibility_rule, leaves.data ?? []),
        // Only an ENCOUNTER option may carry a risk level or opponent lines; the
        // backend rejects them on any other kind, so a re-kinded option sends none.
        encounter_risk_level: draft.option_kind === 'encounter' ? draft.encounter_risk_level : '',
        opponent_lines:
          draft.option_kind === 'encounter'
            ? opponentLineDraftsToPayload(draft.opponent_lines)
            : [],
        // authored_check_type resolves a CHECK (AUTHORED source) or a CONTEST;
        // every other kind forbids it, so a re-kinded option sends null.
        authored_check_type:
          (isCheck && draft.source_kind === 'authored') || isContest
            ? draft.authored_check_type
            : null,
        // opposition_sheet/opposition_check_type are CONTEST-only (#3568).
        opposition_sheet: isContest ? draft.opposition_sheet : null,
        opposition_check_type: isContest ? draft.opposition_check_type : null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: [...missionKeys.options(), 'detail', option.id],
      });
      qc.invalidateQueries({ queryKey: missionKeys.options() });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Option settings</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {serverChanged ? (
          <ServerChangedBanner onPull={pullFromServer} className="md:col-span-2" />
        ) : null}
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
        {/* Base risk is a CHECK-only field - it hides for BRANCH and ENCOUNTER
            the same way (an encounter's risk comes from encounter_risk_level). */}
        {isCheck ? (
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
        ) : null}
        {/* authored_check_type resolves an AUTHORED CHECK or a CONTEST (#3568). */}
        {isCheck || isContest ? (
          <div>
            <Label htmlFor="opt-check-type">Check type</Label>
            <Select
              value={
                draft.authored_check_type !== null ? String(draft.authored_check_type) : 'none'
              }
              onValueChange={(v) =>
                setDraft({
                  ...draft,
                  authored_check_type: v === 'none' ? null : Number(v),
                })
              }
            >
              <SelectTrigger id="opt-check-type">
                <SelectValue placeholder="Select a check type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Unset</SelectItem>
                {checkTypes.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        {isContest ? (
          <div>
            <Label htmlFor="opt-opposition-sheet">Opposition sheet id</Label>
            <Input
              id="opt-opposition-sheet"
              type="number"
              min={1}
              value={draft.opposition_sheet ?? ''}
              onChange={(e) =>
                setDraft({
                  ...draft,
                  opposition_sheet: e.target.value === '' ? null : Number(e.target.value),
                })
              }
            />
          </div>
        ) : null}
        {isContest ? (
          <div>
            <Label htmlFor="opt-opposition-check-type">Opposition check type</Label>
            <Select
              value={
                draft.opposition_check_type !== null ? String(draft.opposition_check_type) : 'none'
              }
              onValueChange={(v) =>
                setDraft({
                  ...draft,
                  opposition_check_type: v === 'none' ? null : Number(v),
                })
              }
            >
              <SelectTrigger id="opt-opposition-check-type">
                <SelectValue placeholder="Select a check type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Unset</SelectItem>
                {checkTypes.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
        {isEncounter ? (
          <div>
            <Label htmlFor="opt-encounter-risk">Encounter risk level</Label>
            <Select
              value={draft.encounter_risk_level || 'none'}
              onValueChange={(v) =>
                setDraft({
                  ...draft,
                  encounter_risk_level: v === 'none' ? '' : (v as (typeof RISK_LEVELS)[number]),
                })
              }
            >
              <SelectTrigger id="opt-encounter-risk">
                <SelectValue placeholder="Select a risk level" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">Unset</SelectItem>
                {RISK_LEVELS.map((r) => (
                  <SelectItem key={r} value={r}>
                    {r}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        ) : null}
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
        {isEncounter ? (
          <div className="border-t pt-3 md:col-span-2">
            <OpponentLinesEditor
              lines={draft.opponent_lines}
              onChange={(lines) => setDraft({ ...draft, opponent_lines: lines })}
              rowErrors={undefined}
            />
          </div>
        ) : null}
        <div className="border-t pt-3 md:col-span-2">
          <PredicateBuilder
            label="Visibility rule"
            value={draft.visibility_rule}
            onChange={(next) => setDraft({ ...draft, visibility_rule: next })}
          />
        </div>
        {!ruleValid && dirty ? (
          <div
            className="rounded border border-destructive/60 bg-destructive/10 px-3 py-2 text-sm text-destructive md:col-span-2"
            data-testid="visibility-rule-errors"
          >
            <div className="font-medium">Visibility rule is not safe to save:</div>
            <ul className="list-inside list-disc">
              {ruleErrors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {mutation.error ? (
          <div className="text-sm text-destructive md:col-span-2" data-testid="option-save-error">
            {String(mutation.error.message)}
          </div>
        ) : null}
        <div className="flex items-center justify-end gap-2 md:col-span-2">
          <Button
            onClick={() => mutation.mutate()}
            disabled={!dirty || !ruleValid || mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
