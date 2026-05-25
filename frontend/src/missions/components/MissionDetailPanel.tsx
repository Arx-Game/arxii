/**
 * MissionDetailPanel — shows a single MissionTemplate's full footprint.
 *
 * §5: list fields + lifetime completions + active instances. Surfaces
 * `access_tier` prominently (the publish gate) plus the categories
 * pills, the level band, and a quick read of active runs (instance id,
 * current node, contract holder).
 *
 * E1 ships read-only; mutation surfaces (access-tier flip, copy, assign)
 * land in E6 and reuse the mutation hooks already in queries.ts.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { useMissionTemplate } from '../queries';

interface MissionDetailPanelProps {
  /** Template slug — the URL key for the detail endpoint. */
  slug: string | undefined;
}

export function MissionDetailPanel({ slug }: MissionDetailPanelProps) {
  const { data: template, isLoading, error } = useMissionTemplate(slug);

  if (!slug) {
    return (
      <Card>
        <CardContent className="p-6 text-muted-foreground">
          Select a mission to view its details.
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <Card>
        <CardContent className="space-y-3 p-6">
          <Skeleton className="h-6 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-32 w-full" />
        </CardContent>
      </Card>
    );
  }

  if (error || !template) {
    return (
      <Card>
        <CardContent className="p-6 text-destructive">Failed to load mission {slug}.</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <CardTitle>{template.name}</CardTitle>
          <AccessTierBadge tier={template.access_tier ?? 'staff_only'} />
        </div>
        <div className="text-xs text-muted-foreground">{template.slug}</div>
      </CardHeader>
      <CardContent className="space-y-4">
        <DescriptionBlock label="Summary" text={template.summary} />
        {template.epilogue ? <DescriptionBlock label="Epilogue" text={template.epilogue} /> : null}
        <MetadataGrid template={template} />
        <CategoriesRow categories={template.categories ?? []} />
        <FootprintBlock
          lifetimeCompletions={template.lifetime_completions}
          activeInstances={
            (template.active_instances ?? []) as unknown as readonly ActiveInstance[]
          }
        />
      </CardContent>
    </Card>
  );
}

function AccessTierBadge({ tier }: { tier: 'open' | 'staff_only' }) {
  if (tier === 'open') {
    return <Badge variant="default">Open</Badge>;
  }
  return (
    <Badge variant="secondary" data-testid="access-tier-staff-only">
      Staff only
    </Badge>
  );
}

function DescriptionBlock({ label, text }: { label: string; text: string }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <p className="mt-1 whitespace-pre-wrap text-sm">{text}</p>
    </div>
  );
}

function MetadataGrid({
  template,
}: {
  template: {
    level_band_min: number;
    level_band_max: number;
    risk_tier: number;
    arc_scope: string;
    is_active?: boolean;
  };
}) {
  return (
    <div className="grid grid-cols-2 gap-3 text-sm md:grid-cols-4">
      <Cell label="Level band">
        {template.level_band_min}–{template.level_band_max}
      </Cell>
      <Cell label="Risk tier">{template.risk_tier}</Cell>
      <Cell label="Arc scope">{template.arc_scope}</Cell>
      <Cell label="Active">{template.is_active === false ? 'No' : 'Yes'}</Cell>
    </div>
  );
}

function Cell({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-1">{children}</div>
    </div>
  );
}

function CategoriesRow({ categories }: { categories: readonly string[] }) {
  if (categories.length === 0) {
    return <div className="text-xs text-muted-foreground">No categories assigned.</div>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {categories.map((c) => (
        <Badge key={c} variant="outline">
          {c}
        </Badge>
      ))}
    </div>
  );
}

interface ActiveInstance {
  instance_id: number;
  current_node_key: string | null;
  contract_holder: string | null;
}

function FootprintBlock({
  lifetimeCompletions,
  activeInstances,
}: {
  lifetimeCompletions: number;
  activeInstances: readonly ActiveInstance[];
}) {
  return (
    <div className="border-t pt-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Lifetime completions
          </div>
          <div className="text-2xl font-semibold">{lifetimeCompletions}</div>
        </div>
        <div>
          <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Active runs
          </div>
          <div className="text-2xl font-semibold">{activeInstances.length}</div>
        </div>
      </div>
      {activeInstances.length > 0 ? (
        <ul className="mt-3 space-y-1 text-sm" data-testid="active-instances-list">
          {activeInstances.map((row) => (
            <li
              key={row.instance_id}
              className="flex justify-between gap-2 rounded border bg-muted/30 px-2 py-1"
            >
              <span>
                #{row.instance_id} @ {row.current_node_key ?? '<no node>'}
              </span>
              <span className="text-muted-foreground">{row.contract_holder ?? '<unowned>'}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
