/**
 * BattleWriteupPage — Wikipedia-style historical writeup for a concluded battle (#1735).
 *
 * Route: /battles/:id
 *
 * Unlike the live strategic battle map (BattleMapPage at /scenes/:id/battle), this
 * is a read-only post-conclusion summary: forces, outcome, participants, places,
 * and legendary deeds. Reuses useBattleDetailQuery (same BattleDetailSerializer
 * endpoint) per docs/systems/battles.md's guidance to not author a second
 * aggregate.
 */
import { Link, useParams } from 'react-router-dom';

import { useBattleDetailQuery } from '../queries';
import type { BattleDeed, BattleDetail } from '../types';

const OUTCOME_LABELS: Record<string, string> = {
  unresolved: 'Unresolved',
  attacker_decisive: 'Attacker — decisive',
  attacker_marginal: 'Attacker — marginal',
  defender_marginal: 'Defender — marginal',
  defender_decisive: 'Defender — decisive',
};

function formatDate(iso: string | null | undefined): string | null {
  if (!iso) return null;
  try {
    return new Date(iso).toLocaleDateString('en-US', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  } catch {
    return null;
  }
}

export function BattleWriteupPage() {
  const { id = '' } = useParams();
  const battleId = Number(id);
  const {
    data: battle,
    isLoading,
    isError,
  } = useBattleDetailQuery(Number.isNaN(battleId) ? null : battleId);

  if (isLoading) {
    return (
      <div className="p-4 text-sm text-muted-foreground" data-testid="battle-writeup-loading">
        Loading battle writeup…
      </div>
    );
  }

  if (isError || !battle) {
    return (
      <div className="p-4 text-sm text-destructive" data-testid="battle-writeup-error">
        Failed to load the battle writeup.
      </div>
    );
  }

  const deeds = (battle as BattleDetail & { deeds?: BattleDeed[] }).deeds ?? [];
  const outcomeLabel =
    OUTCOME_LABELS[battle.outcome ?? 'unresolved'] ?? battle.outcome ?? 'Unknown';
  const concluded = formatDate(battle.concluded_at as string | null | undefined);
  const created = formatDate(battle.created_at as string | null | undefined);

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-4" data-testid="battle-writeup-page">
      {/* Header */}
      <div data-testid="battle-writeup-header">
        <h1 className="text-2xl font-bold">{battle.name}</h1>
        <div className="mt-1 flex items-center gap-2">
          <span
            className="rounded px-2 py-0.5 text-xs font-medium"
            data-testid="battle-writeup-outcome"
          >
            {outcomeLabel}
          </span>
          {battle.risk_level && (
            <span
              className="rounded bg-muted px-2 py-0.5 text-xs"
              data-testid="battle-writeup-risk"
            >
              {battle.risk_level}
            </span>
          )}
        </div>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap gap-4 text-sm text-muted-foreground">
        {created && <span data-testid="battle-writeup-created">Fought on {created}</span>}
        {concluded && <span data-testid="battle-writeup-concluded">Concluded on {concluded}</span>}
        {battle.scene_id && (
          <Link
            to={`/scenes/${battle.scene_id}`}
            className="text-blue-600 hover:underline"
            data-testid="battle-writeup-scene-link"
          >
            View Scene
          </Link>
        )}
      </div>

      {/* Sides */}
      <section data-testid="battle-writeup-sides">
        <h2 className="mb-2 text-lg font-semibold">Forces</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          {battle.sides.map((side) => (
            <div key={side.id} className="rounded-lg border p-3" data-testid="battle-writeup-side">
              <div className="mb-2 flex items-center gap-2">
                <span className="font-medium">
                  {side.role === 'attacker' ? 'Attackers' : 'Defenders'}
                </span>
                {side.covenant_name && (
                  <span className="text-xs text-muted-foreground">{side.covenant_name}</span>
                )}
              </div>
              <div className="text-xs text-muted-foreground">
                VP: {side.victory_points}/{side.victory_threshold} · {side.posture}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Participants */}
      <section data-testid="battle-writeup-participants">
        <h2 className="mb-2 text-lg font-semibold">Participants</h2>
        <div className="flex flex-wrap gap-3">
          {battle.participants.map((p) => (
            <div
              key={p.id}
              className="flex items-center gap-2 rounded border px-3 py-1"
              data-testid="battle-writeup-participant"
            >
              {p.persona?.thumbnail_media_url && (
                <img
                  src={p.persona.thumbnail_media_url}
                  alt={p.persona.name}
                  className="h-8 w-8 rounded-full object-cover"
                />
              )}
              <span className="text-sm">{p.persona?.name ?? 'Unknown'}</span>
            </div>
          ))}
        </div>
      </section>

      {/* Places */}
      {battle.places.length > 0 && (
        <section data-testid="battle-writeup-places">
          <h2 className="mb-2 text-lg font-semibold">Battlefield</h2>
          <div className="space-y-2">
            {battle.places.map((place) => (
              <div
                key={place.id}
                className="rounded border p-2 text-sm"
                data-testid="battle-writeup-place"
              >
                <span className="font-medium">{place.name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{place.terrain_type}</span>
                {place.fortifications.length > 0 && (
                  <div className="mt-1 text-xs text-muted-foreground">
                    Fortifications: {place.fortifications.map((f) => f.kind).join(', ')}
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Deeds */}
      <section data-testid="battle-writeup-deeds-section">
        <h2 className="mb-2 text-lg font-semibold">Legendary Deeds</h2>
        {deeds.length > 0 ? (
          <div className="space-y-2" data-testid="battle-writeup-deeds">
            {deeds.map((deed) => (
              <div key={deed.id} className="rounded border p-3" data-testid="battle-writeup-deed">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{deed.title}</span>
                  <span className="text-xs text-muted-foreground">
                    {deed.persona?.name ?? 'Unknown'}
                  </span>
                </div>
                {deed.description && (
                  <p className="mt-1 text-sm text-muted-foreground">{deed.description}</p>
                )}
                <div className="mt-1 text-xs text-muted-foreground">
                  Legend value: {deed.base_value}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground" data-testid="battle-writeup-deeds-empty">
            No legendary deeds have been recorded for this battle yet.
          </p>
        )}
      </section>
    </div>
  );
}
