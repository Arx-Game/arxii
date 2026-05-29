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

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { Pencil } from 'lucide-react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { EditCategoriesDialog } from './EditCategoriesDialog';
import { FlavorRewriteCard } from './FlavorRewriteCard';
import { StaffActionsCard } from './StaffActionsCard';
import { TemplateRuleSection } from './TemplateRuleSection';
import { useDeleteMissionInstance, useMissionCategories, useMissionTemplate } from '../queries';

const EMPTY_CATEGORIES: readonly number[] = [];

interface MissionDetailPanelProps {
  /** Template id — the PK for the detail endpoint. */
  id: number | undefined;
}

export function MissionDetailPanel({ id }: MissionDetailPanelProps) {
  const { data: template, isLoading, isError } = useMissionTemplate(id);
  const [editOpen, setEditOpen] = useState(false);

  if (!id) {
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

  if (isError || !template) {
    return (
      <Card>
        <CardContent className="p-6 text-destructive">Failed to load mission #{id}.</CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle>{template.name}</CardTitle>
            <AccessTierBadge tier={template.access_tier ?? 'staff_only'} />
          </div>
          <div className="flex items-center justify-between gap-2">
            <div className="text-xs text-muted-foreground">#{template.id}</div>
            <Button asChild size="sm" variant="outline">
              <Link to={`/staff/missions/${template.id}/canvas`}>Graph view →</Link>
            </Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <DescriptionBlock label="Summary" text={template.summary} />
          {template.epilogue ? (
            <DescriptionBlock label="Epilogue" text={template.epilogue} />
          ) : null}
          <MetadataGrid template={template} />
          <div className="flex items-start gap-2">
            <div className="flex-1">
              <CategoriesRow categories={template.categories ?? EMPTY_CATEGORIES} />
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setEditOpen(true)}
              aria-label="Edit categories"
            >
              <Pencil className="h-4 w-4" />
            </Button>
          </div>
          <EditCategoriesDialog
            open={editOpen}
            onOpenChange={setEditOpen}
            templateId={template.id}
            initialCategories={template.categories ?? EMPTY_CATEGORIES}
          />
          <FootprintBlock
            lifetimeCompletions={template.lifetime_completions}
            activeInstances={
              (template.active_instances ?? []) as unknown as readonly ActiveInstance[]
            }
          />
        </CardContent>
      </Card>
      <StaffActionsCard template={template} />
      <TemplateRuleSection template={template} />
      <FlavorRewriteCard template={template} />
    </div>
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

function CategoriesRow({ categories }: { categories: readonly number[] }) {
  const { data } = useMissionCategories();
  const byId = new Map((data?.results ?? []).map((c) => [c.id, c]));
  if (categories.length === 0) {
    return <div className="text-xs text-muted-foreground">No categories assigned.</div>;
  }
  return (
    <div className="flex flex-wrap gap-1">
      {categories.map((catId) => {
        const cat = byId.get(catId);
        return (
          <Badge key={catId} variant="secondary">
            {cat?.name ?? `#${catId}`}
          </Badge>
        );
      })}
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
  const del = useDeleteMissionInstance();
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
              className="flex items-center justify-between gap-2 rounded border bg-muted/30 px-2 py-1"
            >
              <span className="flex-1">
                #{row.instance_id} @ {row.current_node_key ?? '<no node>'}
              </span>
              <span className="text-muted-foreground">{row.contract_holder ?? '<unowned>'}</span>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  if (confirm(`Delete stuck instance #${row.instance_id}?`)) {
                    del.mutate(row.instance_id);
                  }
                }}
                disabled={del.isPending}
                aria-label={`Delete instance ${row.instance_id}`}
                data-testid={`delete-instance-${row.instance_id}`}
              >
                ✕
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
