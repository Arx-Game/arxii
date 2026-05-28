/**
 * MissionCanvasPage — fullscreen MissionCanvas for one template.
 *
 * Routes: /staff/missions/:id/canvas. Hits the detail endpoint once
 * for the template id (canvas needs it for the per-template filters).
 */

import { Link, useParams } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';

import { MissionCanvas } from '../components/MissionCanvas';
import { useMissionTemplate } from '../queries';

export function MissionCanvasPage() {
  const { id: idStr } = useParams<{ id: string }>();
  const id = idStr ? Number(idStr) : undefined;
  const { data: template, isLoading } = useMissionTemplate(id);

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
