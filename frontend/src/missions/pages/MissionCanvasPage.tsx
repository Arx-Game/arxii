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

import { Link, useLocation, useNavigate, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

import { MissionCanvas } from '../components/MissionCanvas';
import { useMissionTemplate } from '../queries';
import { studioBaseFromPath, studioPaths } from '../studioPaths';

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
      </div>
      {isLoading ? (
        <Card>
          <CardContent className="p-6 text-muted-foreground">Loading…</CardContent>
        </Card>
      ) : (
        <MissionCanvas templateId={id} />
      )}
    </div>
  );
}
