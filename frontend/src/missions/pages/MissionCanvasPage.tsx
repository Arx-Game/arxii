/**
 * MissionCanvasPage — fullscreen MissionCanvas for one template.
 *
 * Routes: /staff/missions/:id/canvas. Hits the detail endpoint once
 * for the template id (canvas needs it for the per-template filters).
 */

import { Link, useNavigate, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

import { MissionCanvas } from '../components/MissionCanvas';
import { useMissionTemplate } from '../queries';

export function MissionCanvasPage() {
  const { id: idStr } = useParams<{ id: string }>();
  // Guard against non-numeric route params (e.g. /canvas/abc → Number("abc") = NaN).
  // useMissionTemplate's enabled guard would disable the query on NaN, leaving the
  // page in a silent "nothing renders" state; show an explicit error card instead.
  const id = idStr && Number.isFinite(Number(idStr)) ? Number(idStr) : undefined;
  const { data: template, isLoading, isError } = useMissionTemplate(id);
  const navigate = useNavigate();

  if (id === undefined) {
    return (
      <div className="container mx-auto max-w-3xl px-4 py-6">
        <div
          className="rounded border border-destructive bg-destructive/10 p-4 text-sm"
          role="alert"
        >
          <p className="font-medium">Missing or invalid id in URL.</p>
          <Button variant="outline" className="mt-3" onClick={() => navigate('/staff/missions')}>
            ← Back to Mission Studio
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
          <p className="font-medium">Couldn't load this mission.</p>
          <p className="mt-1 text-muted-foreground">
            The mission may not exist or you may not have access.
          </p>
          <Button variant="outline" className="mt-3" onClick={() => navigate('/staff/missions')}>
            ← Back to Mission Studio
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
            <Link to={`/staff/missions?id=${id ?? ''}`}>← Back to browser</Link>
          </Button>
          <h1 className="mt-1 text-2xl font-semibold">{template?.name ?? `#${id}`} — Graph</h1>
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
