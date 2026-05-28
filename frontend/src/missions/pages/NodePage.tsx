/**
 * NodePage — edit one MissionNode, list its authored options.
 *
 * Routes: /staff/missions/:slug/nodes/:nodeId. PATCH on save via D2's
 * MissionNodeViewSet. Options listed with click-through to OptionPage.
 *
 * Scope (E3): node settings + flavor text + option list. Cross-tool
 * picker for attached_challenges and challenge-contributed-option
 * preview deferred until those tools land. PredicateBuilder for
 * visibility_rule will hook into OptionPage in E4.
 */

import { Link, useParams } from 'react-router-dom';
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
  useMissionOptions,
  useMissionTemplate,
  usePatchMissionNode,
} from '../queries';
import type { MissionNode } from '../types';
import { useQuery } from '@tanstack/react-query';

const CONFLICT_MODES: Array<MissionNode['conflict_mode']> = ['coinflip', 'vote', 'joint'];

export function NodePage() {
  const { id: idStr, nodeId } = useParams<{ id: string; nodeId: string }>();
  const templateId = idStr ? Number(idStr) : undefined;
  const numericNodeId = Number(nodeId);
  const { data: template } = useMissionTemplate(templateId);
  const { data: node, isLoading } = useNode(numericNodeId);
  const { data: optionsPage } = useMissionOptions({ node: numericNodeId });

  if (Number.isNaN(numericNodeId)) {
    return <div className="p-6 text-destructive">Bad node id.</div>;
  }

  return (
    <div className="container mx-auto space-y-4 px-4 py-6">
      <StudioBreadcrumb
        crumbs={[
          { label: 'Missions', to: '/staff/missions' },
          {
            label: template?.name ?? (templateId ? `#${templateId}` : '…'),
            to: `/staff/missions?id=${templateId ?? ''}`,
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
                to={`/staff/missions/${templateId}/nodes/${numericNodeId}/options/${opt.id}`}
                className="flex items-center justify-between rounded border px-2 py-1 text-sm hover:bg-muted"
              >
                <span>
                  #{opt.order} — {opt.option_kind} / {opt.source_kind}
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
    throwOnError: true,
  });
}

function NodeEditor({ node }: { node: MissionNode }) {
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(node, (n) => ({
    key: n.key,
    flavor_text: n.flavor_text ?? '',
    flavor_text_needs_rewrite: n.flavor_text_needs_rewrite ?? false,
    conflict_mode: n.conflict_mode,
    is_entry: n.is_entry ?? false,
  }));
  const patchNode = usePatchMissionNode();
  const qc = useQueryClient();

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
        <div className="flex items-center justify-end gap-2 md:col-span-2">
          <Button onClick={onSave} disabled={!dirty || patchNode.isPending}>
            {patchNode.isPending ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
