/**
 * FlavorRewriteCard — surface every node/option/route in a template
 * whose flavor was marked needs_rewrite (e.g. inherited from a copy).
 *
 * Lives below the MissionDetailPanel. Three lists, each query-scoped
 * to the parent template by `?template=<pk>&needs_rewrite=true`. Each
 * row links to the appropriate editor page so authors can jump
 * straight to the field that needs work.
 *
 * Nothing is mutated here — this is a navigation surface. Clearing the
 * flag happens by editing the field on NodePage / OptionPage (the
 * `needs_rewrite` switch on each editor).
 */

import { Link } from 'react-router-dom';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

import { useMissionNodes, useMissionOptions, useMissionRoutes } from '../queries';
import type { MissionTemplate } from '../types';

interface FlavorRewriteCardProps {
  template: MissionTemplate;
}

export function FlavorRewriteCard({ template }: FlavorRewriteCardProps) {
  const nodes = useMissionNodes({ template: template.id, needs_rewrite: true });
  const options = useMissionOptions({ template: template.id, needs_rewrite: true });
  const routes = useMissionRoutes({ template: template.id, needs_rewrite: true });

  const nodeRows = nodes.data?.results ?? [];
  const optionRows = options.data?.results ?? [];
  const routeRows = routes.data?.results ?? [];
  const total = nodeRows.length + optionRows.length + routeRows.length;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>Flavor needs rewrite</span>
          <Badge variant={total > 0 ? 'destructive' : 'outline'} data-testid="rewrite-count">
            {total}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3" data-testid="rewrite-card">
        {nodes.isLoading || options.isLoading || routes.isLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : total === 0 ? (
          <div className="text-sm text-muted-foreground">All flavor text is clear.</div>
        ) : (
          <>
            {nodeRows.length > 0 ? (
              <Section title={`Nodes (${nodeRows.length})`}>
                {nodeRows.map((n) => (
                  <Link
                    key={n.id}
                    to={`/staff/missions/${template.id}/nodes/${n.id}`}
                    className="block rounded border px-2 py-1 text-sm hover:bg-muted"
                  >
                    {n.key}
                  </Link>
                ))}
              </Section>
            ) : null}
            {optionRows.length > 0 ? (
              <Section title={`Options (${optionRows.length})`}>
                {optionRows.map((o) => (
                  <Link
                    key={o.id}
                    to={`/staff/missions/${template.id}/nodes/${o.node}/options/${o.id}`}
                    className="block rounded border px-2 py-1 text-sm hover:bg-muted"
                  >
                    Node {o.node} · option #{o.order} ({o.option_kind})
                  </Link>
                ))}
              </Section>
            ) : null}
            {routeRows.length > 0 ? (
              <Section title={`Routes (${routeRows.length})`}>
                {routeRows.map((r) => (
                  <div
                    key={r.id}
                    className="rounded border px-2 py-1 text-sm text-muted-foreground"
                  >
                    Route id={r.id} (option {r.option}) — outcome {r.outcome_tier ?? '<branch>'}
                  </div>
                ))}
              </Section>
            ) : null}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {title}
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}
