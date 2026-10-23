/**
 * MissionCanvasPage — fullscreen MissionCanvas for one template.
 *
 * Mounted twice: /staff/missions/:id/canvas (StaffRoute) and
 * /stories/scenarios/:id/canvas (GMRoute, #3565) - studioPaths derives
 * which mount is live from the current URL so every link on the page
 * stays on the right side. Hits the detail endpoint once for the
 * template id (canvas needs it for the per-template filters, and the
 * scenario mount needs template.story_id for the browser link).
 */

import { useState } from 'react';
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

import { AddNodeDialog } from '../components/AddNodeDialog';
import { MissionCanvas } from '../components/MissionCanvas';
import { useGraphCheck, useMissionNodes, useMissionOptions, useMissionTemplate } from '../queries';
import { studioBaseFromPath, studioPaths, type StudioPaths } from '../studioPaths';
import type { GraphProblem } from '../types';

function problemLink(
  p: GraphProblem,
  nodeId: number | undefined,
  paths: StudioPaths
): string | null {
  if (nodeId === undefined) return null;
  return p.option !== null ? paths.option(nodeId, p.option) : paths.node(nodeId);
}

function ProblemsPanel({
  problems,
  loaded,
  paths,
  optionNode,
}: {
  problems: readonly GraphProblem[];
  /** False until the graph check answers, so a loading panel never says all is well. */
  loaded: boolean;
  paths: StudioPaths;
  optionNode: ReadonlyMap<number, number>;
}) {
  return (
    <section aria-label="Problems" className="rounded border p-3 text-sm">
      <h2 className="font-medium">Problems</h2>
      {loaded && problems.length === 0 ? (
        <p className="text-muted-foreground">No problems found.</p>
      ) : null}
      {loaded && problems.length > 0 ? (
        <ul className="mt-1 space-y-1">
          {problems.map((p, i) => {
            const nodeId = p.node ?? (p.option !== null ? optionNode.get(p.option) : undefined);
            const to = problemLink(p, nodeId, paths);
            return (
              <li key={`${p.kind}-${i}`}>
                {to ? (
                  <Link className="underline" to={to}>
                    {p.message}
                  </Link>
                ) : (
                  p.message
                )}
              </li>
            );
          })}
        </ul>
      ) : null}
    </section>
  );
}

export function MissionCanvasPage() {
  const { id: idStr } = useParams<{ id: string }>();
  // Guard against non-numeric route params (e.g. /canvas/abc → Number("abc") = NaN).
  // useMissionTemplate's enabled guard would disable the query on NaN, leaving the
  // page in a silent "nothing renders" state; show an explicit error card instead.
  const id = idStr && Number.isFinite(Number(idStr)) ? Number(idStr) : undefined;
  const { data: template, isLoading, isError } = useMissionTemplate(id);
  const navigate = useNavigate();
  const location = useLocation();
  const base = studioBaseFromPath(location.pathname);
  const paths = studioPaths(base, id ?? 0, template?.story_id);
  const [addOpen, setAddOpen] = useState(false);
  const nodesQuery = useMissionNodes({ template: id });
  const optionsQuery = useMissionOptions({ template: id });
  const problemsQuery = useGraphCheck(id);
  const optionNode = new Map<number, number>();
  for (const opt of optionsQuery.data?.results ?? []) optionNode.set(opt.id, opt.node);
  const noun = base === 'scenario' ? 'scenario' : 'mission';

  if (id === undefined) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <div
          className="rounded border border-destructive bg-destructive/10 p-4 text-sm"
          role="alert"
        >
          <p className="font-medium">Missing or invalid id in URL.</p>
          <Button variant="outline" className="mt-3" onClick={() => navigate(paths.browser)}>
            ← Back to {paths.browserLabel}
          </Button>
        </div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <div
          className="rounded border border-destructive bg-destructive/10 p-4 text-sm"
          role="alert"
        >
          <p className="font-medium">Couldn't load this {noun}.</p>
          <p className="mt-1 text-muted-foreground">
            The {noun} may not exist or you may not have access.
          </p>
          <Button variant="outline" className="mt-3" onClick={() => navigate(paths.browser)}>
            ← Back to {paths.browserLabel}
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="container mx-auto space-y-3 px-4 py-6">
      <div className="flex items-center justify-between">
        <div>
          <Button asChild variant="ghost" size="sm">
            <Link to={paths.browser}>← Back to browser</Link>
          </Button>
          <h1 className="mt-1 text-2xl font-semibold">
            {template?.name ?? `#${id}`}: {base === 'scenario' ? 'Scenario graph' : 'Graph'}
          </h1>
        </div>
        <Button onClick={() => setAddOpen(true)}>Add node</Button>
      </div>
      <ProblemsPanel
        problems={problemsQuery.data ?? []}
        loaded={problemsQuery.isSuccess}
        paths={paths}
        optionNode={optionNode}
      />
      <AddNodeDialog
        open={addOpen}
        onOpenChange={setAddOpen}
        templateId={id}
        isFirstNode={nodesQuery.data !== undefined && nodesQuery.data.results.length === 0}
      />
      {isLoading ? (
        <Card>
          <CardContent className="p-6 text-muted-foreground">Loading…</CardContent>
        </Card>
      ) : (
        <MissionCanvas templateId={id} paths={paths} />
      )}
    </div>
  );
}
