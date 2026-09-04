/**
 * ScenarioCard - the mission scenario a scene's beats run on (#3565).
 *
 * Fetches `GET /api/scenes/{id}/scenario/` (`useSceneScenarioQuery`). Renders
 * nothing when there is no running instance, or when the viewer is not a
 * participant on it - the card self-hides rather than erroring, mirroring
 * `GMStoryRail`'s tolerate-and-hide convention. While an active encounter has
 * the scenario paused, shows a plain notice instead of the group-beat card;
 * otherwise mounts the existing `GroupBeatCard` (missions system, #1036),
 * whose own polling drives picks and votes through the unchanged journal
 * endpoints.
 */

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { GroupBeatCard } from '@/missions/components/GroupBeatCard';
import { useSceneScenarioQuery } from '../queries';
import type { SceneDetail } from '../types';

export interface ScenarioCardProps {
  scene: SceneDetail;
}

export function ScenarioCard({ scene }: ScenarioCardProps) {
  const { data: scenario } = useSceneScenarioQuery(String(scene.id), scene.is_active);

  if (!scenario || scenario.instance_id === null || !scenario.viewer_is_participant) {
    return null;
  }

  return (
    <Card className="mb-3" data-testid="scenario-card">
      <CardHeader>
        <CardTitle className="text-base">Scenario</CardTitle>
      </CardHeader>
      <CardContent>
        {scenario.is_paused ? (
          <p className="text-sm text-muted-foreground" data-testid="scenario-card-paused">
            A fight is underway; the scenario continues when it ends.
          </p>
        ) : (
          <GroupBeatCard instanceId={scenario.instance_id} roomKey={`scene-${scene.id}`} />
        )}
      </CardContent>
    </Card>
  );
}
