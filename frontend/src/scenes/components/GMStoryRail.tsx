/**
 * GMStoryRail - the GM story rail (#3434): the running beat's authored
 * material, protected subjects, and participant conditions/vitals, rendered
 * beside the scene so a GM referees against what they designed instead of
 * tabbing to the stories pages mid-scene.
 *
 * Mounted from SceneDetailPage as a `CombatRail`-pattern sibling. Fetches
 * `GET /api/scenes/{id}/gm-rail/` (`useGMStoryRailQuery`), which is gated
 * server-side to staff or a scene GM at JUNIOR+ trust - a viewer who fails
 * that gate simply gets `null` back (mirrors `fetchCharacterVitals`'s
 * tolerate-and-hide convention) and this component renders nothing.
 *
 * Per-participant conditions ride the same non-ViewSet `gm_list_conditions`
 * registry dispatch `GMAdjudicationPanel`'s Condition tab uses (no ViewSet
 * read exposes a target's hidden active conditions to their GM); vitals ride
 * the existing `useCharacterVitalsQuery` hook, which already tolerates a
 * 401/403/404 denial per character by returning null - so one participant's
 * vitals being unavailable never breaks the rest of the rail.
 */

import { useEffect, useMemo, useState } from 'react';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { isDispatchFailure } from '@/combat/types';
import { useCharacterVitalsQuery } from '@/vitals/vitalsQueries';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { GMStoryRailParticipant, SceneDetail } from '../types';
import { useGMStoryRailQuery } from '../queries';

interface RailConditionEntry {
  id: number;
  name: string;
  severity: number;
}

interface ParticipantRowProps {
  participant: GMStoryRailParticipant;
  actorCharacterId: number | null;
}

function ParticipantRow({ participant, actorCharacterId }: ParticipantRowProps) {
  const dispatch = useDispatchPlayerAction(actorCharacterId ?? 0);
  const [conditions, setConditions] = useState<RailConditionEntry[]>([]);
  const [conditionsUnavailable, setConditionsUnavailable] = useState(false);
  const { data: vitals } = useCharacterVitalsQuery(participant.character_sheet_id);

  useEffect(() => {
    if (actorCharacterId === null) return;
    dispatch
      .mutateAsync({
        ref: { backend: 'registry', registry_key: 'gm_list_conditions' },
        kwargs: { target: participant.character_sheet_id },
      })
      .then((result) => {
        if (isDispatchFailure(result)) {
          setConditionsUnavailable(true);
          return;
        }
        const data = result.data as { conditions?: RailConditionEntry[] } | null | undefined;
        setConditions(data?.conditions ?? []);
      })
      .catch(() => setConditionsUnavailable(true));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [participant.character_sheet_id, actorCharacterId]);

  const renderConditionsUnavailable = () => {
    if (conditionsUnavailable) {
      return <div className="text-xs text-muted-foreground">Conditions unavailable.</div>;
    }
    if (conditions.length > 0) {
      return (
        <ul className="text-xs text-muted-foreground" data-testid="gm-rail-participant-conditions">
          {conditions.map((c) => (
            <li key={c.id}>
              {c.name} (severity {c.severity})
            </li>
          ))}
        </ul>
      );
    }
    return <div className="text-xs text-muted-foreground">No active conditions.</div>;
  };

  return (
    <div
      className="rounded border p-2 text-sm"
      data-testid={`gm-rail-participant-${participant.character_sheet_id}`}
    >
      <div className="font-medium">{participant.name}</div>
      {vitals ? (
        <div className="text-xs text-muted-foreground" data-testid="gm-rail-participant-vitals">
          HP {vitals.health}/{vitals.max_health} - {vitals.status}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground">Vitals unavailable.</div>
      )}
      {renderConditionsUnavailable()}
    </div>
  );
}

export interface GMStoryRailProps {
  scene: SceneDetail;
}

export function GMStoryRail({ scene }: GMStoryRailProps) {
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const actorCharacterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const hasRunningBeat = scene.running_beat != null;
  const { data: rail } = useGMStoryRailQuery(String(scene.id), hasRunningBeat);

  if (!scene.viewer_can_gm) {
    return null;
  }

  if (!hasRunningBeat) {
    return (
      <Card data-testid="gm-story-rail">
        <CardHeader>
          <CardTitle className="text-base">Story Rail</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground" data-testid="gm-story-rail-no-beat">
            No beat running - Run one from the panel.
          </p>
        </CardContent>
      </Card>
    );
  }

  // Denied server-side (below JUNIOR trust, or the scene ended between mount
  // and fetch) - render nothing rather than an error state.
  if (rail === null) {
    return null;
  }

  return (
    <Card data-testid="gm-story-rail">
      <CardHeader>
        <CardTitle className="text-base">Story Rail</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {rail?.beat && (
          <div data-testid="gm-story-rail-beat" className="space-y-1 text-sm">
            <div>
              <span className="font-medium">Kind:</span> {rail.beat.kind}
            </div>
            <div>
              <span className="font-medium">Risk:</span> {rail.beat.risk}
            </div>
            <div>
              <span className="font-medium">Outcome:</span> {rail.beat.outcome}
            </div>
            <div>
              <span className="font-medium">Predicate:</span> {rail.beat.predicate_type}
            </div>
            {rail.beat.internal_description !== null && (
              <p className="text-muted-foreground" data-testid="gm-story-rail-internal-description">
                {rail.beat.internal_description}
              </p>
            )}
          </div>
        )}

        {rail && rail.protected_subjects.length > 0 && (
          <div data-testid="gm-story-rail-protected-subjects" className="space-y-1 text-sm">
            <div className="font-medium">Protected Subjects</div>
            <ul className="text-muted-foreground">
              {rail.protected_subjects.map((subject) => (
                <li key={subject.id}>
                  {subject.subject_kind}
                  {subject.subject_label ? `: ${subject.subject_label}` : ''}
                </li>
              ))}
            </ul>
          </div>
        )}

        {rail && rail.clue_placements.length > 0 && (
          <div data-testid="gm-story-rail-clue-placements" className="space-y-1 text-sm">
            <div className="font-medium">Room Clue Placements</div>
            <ul className="text-muted-foreground">
              {rail.clue_placements.map((clue) => (
                <li key={clue.id}>{clue.clue_name}</li>
              ))}
            </ul>
          </div>
        )}

        {rail && rail.participants.length > 0 && (
          <div data-testid="gm-story-rail-participants" className="space-y-2">
            <div className="text-sm font-medium">Participants</div>
            {rail.participants.map((participant) => (
              <ParticipantRow
                key={participant.character_sheet_id}
                participant={participant}
                actorCharacterId={actorCharacterId}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
