/**
 * NodePage — edit one MissionNode, list its authored options.
 *
 * Mounted twice: /staff/missions/:id/nodes/:nodeId (StaffRoute) and
 * /stories/scenarios/:id/nodes/:nodeId (GMRoute, #3565) - studioPaths
 * derives which mount is live from the current URL. PATCH on save via
 * D2's MissionNodeViewSet. Options listed with click-through to
 * OptionPage.
 *
 * Scope (E3): node settings + flavor text + option list. Cross-tool
 * picker for attached_challenges and challenge-contributed-option
 * preview deferred until those tools land. PredicateBuilder for
 * visibility_rule will hook into OptionPage in E4.
 */

import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';

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

import { ServerChangedBanner } from '../components/ServerChangedBanner';
import { StudioBreadcrumb } from '../components/StudioBreadcrumb';
import { getMissionNode } from '../api';
import { useServerDraft } from '../hooks/useServerDraft';
import {
  missionKeys,
  useMissionNodes,
  useMissionOptions,
  useMissionTemplate,
  usePatchMissionNode,
} from '../queries';
import { studioBaseFromPath, studioPaths } from '../studioPaths';
import type { MissionNode } from '../types';
import { useQuery } from '@tanstack/react-query';

const CONFLICT_MODES: Array<MissionNode['conflict_mode']> = ['group_vote', 'joint'];
const BEAT_OUTCOMES: Array<'success' | 'failure'> = ['success', 'failure'];

export function NodePage() {
  const { id: idStr, nodeId } = useParams<{ id: string; nodeId: string }>();
  const templateId = idStr ? Number(idStr) : undefined;
  const numericNodeId = Number(nodeId);
  const { data: template } = useMissionTemplate(templateId);
  const { data: node, isLoading, isError } = useNode(numericNodeId);
  const { data: optionsPage } = useMissionOptions({ node: numericNodeId });
  const navigate = useNavigate();
  const location = useLocation();
  const base = studioBaseFromPath(location.pathname);
  const paths = studioPaths(base, templateId ?? 0, template?.story_id);

  if (Number.isNaN(numericNodeId)) {
    return <div className="p-6 text-destructive">Bad node id.</div>;
  }

  if (isError) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <div
          className="rounded border border-destructive bg-destructive/10 p-4 text-sm"
          role="alert"
        >
          <p className="font-medium">Couldn't load this node.</p>
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
          { label: node ? `Node "${node.key}"` : '…' },
        ]}
      />
      {isLoading || !node ? <Skeleton className="h-64 w-full" /> : <NodeEditor node={node} />}
      <Card>
        <CardHeader>
          <CardTitle>Options on this node</CardTitle>
        </CardHeader>
        <CardContent className="space-y-1" data-testid="node-options-list">
          {optionsPage && optionsPage.results.length > 0 ? (
            optionsPage.results.map((opt) => (
              <Link
                key={opt.id}
                to={
                  templateId !== undefined && Number.isFinite(templateId)
                    ? paths.option(numericNodeId, opt.id)
                    : paths.browser
                }
                className="flex items-center justify-between rounded border px-2 py-1 text-sm hover:bg-muted"
              >
                <span>
                  #{opt.order}: {opt.option_kind} / {opt.source_kind}
                </span>
                <span className="text-xs text-muted-foreground">
                  {opt.authored_ic_framing || '<no framing>'}
                </span>
              </Link>
            ))
          ) : (
            <div className="text-sm text-muted-foreground">No options yet.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

/** Local-only single-node fetcher (no list endpoint detour). */
function useNode(id: number) {
  return useQuery({
    queryKey: [...missionKeys.nodes(), 'detail', id],
    queryFn: () => getMissionNode(id),
    enabled: !Number.isNaN(id) && id > 0,
    // Consumers check isError and render inline so a fetch failure doesn't
    // nuke the whole drill-down view.
  });
}

function NodeEditor({ node }: { node: MissionNode }) {
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(node, (n) => ({
    key: n.key,
    flavor_text: n.flavor_text ?? '',
    flavor_text_needs_rewrite: n.flavor_text_needs_rewrite ?? false,
    conflict_mode: n.conflict_mode,
    is_entry: n.is_entry ?? false,
    track_successes: n.track_successes ?? 0,
    track_failures: n.track_failures ?? 0,
    track_success_target: n.track_success_target ?? null,
    track_failure_target: n.track_failure_target ?? null,
    track_success_beat_outcome: n.track_success_beat_outcome ?? '',
    track_failure_beat_outcome: n.track_failure_beat_outcome ?? '',
  }));
  const patchNode = usePatchMissionNode();
  const qc = useQueryClient();
  // Track targets route to another node in the same template (or terminal
  // when null) - the option-page precedent for a node picker (branch_target)
  // doesn't exist yet, so this is the first one (#3568).
  const { data: otherNodesPage } = useMissionNodes({ template: node.template });
  const otherNodes = (otherNodesPage?.results ?? []).filter((n) => n.id !== node.id);

  const onSave = () => {
    patchNode.mutate(
      { id: node.id, body: draft },
      {
        onSuccess: () =>
          qc.invalidateQueries({
            queryKey: [...missionKeys.nodes(), 'detail', node.id],
          }),
      }
    );
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Node settings</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {serverChanged ? (
          <ServerChangedBanner onPull={pullFromServer} className="md:col-span-2" />
        ) : null}
        <div>
          <Label htmlFor="node-key">Key</Label>
          <Input
            id="node-key"
            value={draft.key}
            onChange={(e) => setDraft({ ...draft, key: e.target.value })}
          />
        </div>
        <div>
          <Label htmlFor="node-conflict">Conflict mode</Label>
          <Select
            value={draft.conflict_mode}
            onValueChange={(v) =>
              setDraft({ ...draft, conflict_mode: v as MissionNode['conflict_mode'] })
            }
          >
            <SelectTrigger id="node-conflict">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {CONFLICT_MODES.map((m) => (
                <SelectItem key={m} value={m}>
                  {m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="md:col-span-2">
          <Label htmlFor="node-flavor">Flavor text</Label>
          <Textarea
            id="node-flavor"
            value={draft.flavor_text}
            onChange={(e) => setDraft({ ...draft, flavor_text: e.target.value })}
            rows={4}
          />
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="node-needs-rewrite"
            checked={draft.flavor_text_needs_rewrite}
            onCheckedChange={(v) => setDraft({ ...draft, flavor_text_needs_rewrite: v })}
          />
          <Label htmlFor="node-needs-rewrite">Flavor needs rewrite</Label>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            id="node-is-entry"
            checked={draft.is_entry}
            onCheckedChange={(v) => setDraft({ ...draft, is_entry: v })}
          />
          <Label htmlFor="node-is-entry">Entry node</Label>
        </div>
        <div className="border-t pt-3 md:col-span-2">
          <div className="mb-2 text-sm font-medium">Progress track</div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="node-track-successes">Successes needed</Label>
              <Input
                id="node-track-successes"
                type="number"
                min={0}
                value={draft.track_successes}
                onChange={(e) =>
                  setDraft({ ...draft, track_successes: Number(e.target.value || 0) })
                }
              />
            </div>
            <div>
              <Label htmlFor="node-track-failures">Failures allowed</Label>
              <Input
                id="node-track-failures"
                type="number"
                min={0}
                value={draft.track_failures}
                onChange={(e) =>
                  setDraft({ ...draft, track_failures: Number(e.target.value || 0) })
                }
              />
            </div>
            <div>
              <Label htmlFor="node-track-success-target">On track success, go to</Label>
              <Select
                value={
                  draft.track_success_target !== null
                    ? String(draft.track_success_target)
                    : 'terminal'
                }
                onValueChange={(v) =>
                  setDraft({
                    ...draft,
                    track_success_target: v === 'terminal' ? null : Number(v),
                  })
                }
              >
                <SelectTrigger id="node-track-success-target">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="terminal">Terminal (end run)</SelectItem>
                  {otherNodes.map((n) => (
                    <SelectItem key={n.id} value={String(n.id)}>
                      {n.key}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="node-track-failure-target">On track failure, go to</Label>
              <Select
                value={
                  draft.track_failure_target !== null
                    ? String(draft.track_failure_target)
                    : 'terminal'
                }
                onValueChange={(v) =>
                  setDraft({
                    ...draft,
                    track_failure_target: v === 'terminal' ? null : Number(v),
                  })
                }
              >
                <SelectTrigger id="node-track-failure-target">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="terminal">Terminal (end run)</SelectItem>
                  {otherNodes.map((n) => (
                    <SelectItem key={n.id} value={String(n.id)}>
                      {n.key}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="node-track-success-outcome">Success beat outcome</Label>
              <Select
                value={draft.track_success_beat_outcome || 'derive'}
                onValueChange={(v) =>
                  setDraft({
                    ...draft,
                    track_success_beat_outcome: v === 'derive' ? '' : (v as 'success' | 'failure'),
                  })
                }
              >
                <SelectTrigger id="node-track-success-outcome">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="derive">(derive)</SelectItem>
                  {BEAT_OUTCOMES.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="node-track-failure-outcome">Failure beat outcome</Label>
              <Select
                value={draft.track_failure_beat_outcome || 'derive'}
                onValueChange={(v) =>
                  setDraft({
                    ...draft,
                    track_failure_beat_outcome: v === 'derive' ? '' : (v as 'success' | 'failure'),
                  })
                }
              >
                <SelectTrigger id="node-track-failure-outcome">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="derive">(derive)</SelectItem>
                  {BEAT_OUTCOMES.map((o) => (
                    <SelectItem key={o} value={o}>
                      {o}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-end gap-2 md:col-span-2">
          <Button onClick={onSave} disabled={!dirty || patchNode.isPending}>
            {patchNode.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
