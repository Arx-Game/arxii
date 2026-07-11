/**
 * RitualProposedChip (#2159 Task 7) — a transient badge shown in the
 * `/game` scene surface (`RoomPanel`) and `SceneDetailPage` while a
 * PENDING/READY `RitualSession` has this scene as its captured origin
 * (`RitualSession.scene`, #2159 Task 5).
 *
 * "Transient by design" — `RitualSession` rows persist only during
 * PENDING/READY; they're deleted outright on fire/cancel/expiry/
 * threshold-killing decline (see the model docstring). So a non-empty
 * result from `useRitualSessionsForScene` already IS the PENDING/READY
 * signal — no separate status field to check, and no persistence work of
 * its own for this chip. Renders nothing while loading, on fetch error, or
 * when no session links the scene.
 */
import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { useRitualSessionsForScene } from '../queries';

export interface RitualProposedChipProps {
  sceneId: number | null;
}

export function RitualProposedChip({ sceneId }: RitualProposedChipProps) {
  const { data: sessions = [] } = useRitualSessionsForScene(sceneId);

  if (sessions.length === 0) return null;

  // Multiple sessions could theoretically link the same scene (e.g. two
  // different rituals drafted in sequence); link the most recently created
  // one — the list is server-ordered `-created_at`.
  const session = sessions[0];

  return (
    <div className="border-b px-3 py-1.5">
      <Link to={`/rituals/sessions/${session.id}`}>
        <Badge variant="secondary" className="text-xs" data-testid="ritual-proposed-chip">
          Ritual proposed: {session.ritual_name}
        </Badge>
      </Link>
    </div>
  );
}
