/**
 * OriginsSection (#3660) — the sheet's origin-story ties, entity-linked and
 * life-stage-tagged.
 *
 * A card per `kind === 'group'` origin slot: the group (linked when it
 * resolved to a real `Organization`), the tie and life-stage tags, the
 * viewer's own standing with that group (own sheet only), any named figures
 * belonging to it, and the picked choice's own text. `text`/`pick` rows carry
 * no entity/stage of their own and are already folded into the prose
 * (`background`), so they render nowhere here.
 *
 * Replaces `BackgroundSection` on `CharacterSheetPage` once a sheet has any
 * origin slots at all (`sheetPayload?.story.origin_slots.length`); a sheet
 * with none still falls back to the plain background paragraph.
 */

import { Link } from 'react-router-dom';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { CharacterSheetOriginSlot, CharacterSheetStory } from '@/character_sheets/api';
import { CONNECTION_KIND_LABELS, LIFE_STAGE_LABELS } from '@/character-creation/types';
import { TIER_VARIANT, formatTier } from '@/renown/components/ReputationListCard';
import { useOrganizationReputationsQuery } from '@/reputation/queries';

interface OriginsSectionProps {
  story: CharacterSheetStory;
  background: string | undefined;
  isMyCharacter: boolean;
}

function tieLabel(row: CharacterSheetOriginSlot): string | null {
  if (!row.connection_kind) return null;
  return CONNECTION_KIND_LABELS[row.connection_kind] ?? row.connection_kind;
}

function stageLabel(row: CharacterSheetOriginSlot): string | null {
  if (!row.life_stage) return null;
  return LIFE_STAGE_LABELS[row.life_stage] ?? row.life_stage;
}

export function OriginsSection({ story, background, isMyCharacter }: OriginsSectionProps) {
  // Own-view only: the endpoint is the requester's own standing, never a
  // foreign viewer's.
  const { data: reputations } = useOrganizationReputationsQuery(isMyCharacter);

  const groupRows = story.origin_slots.filter((row) => row.kind === 'group');

  return (
    <section>
      <h3 className="text-xl font-semibold">Origins</h3>
      {groupRows.length > 0 && (
        <div className="grid gap-3 pb-2 sm:grid-cols-2" data-testid="origin-group-cards">
          {groupRows.map((row) => {
            const tier = reputations?.find((rep) => rep.organization === row.organization_id);
            const personRows = story.origin_slots.filter(
              (candidate) =>
                candidate.kind === 'person' &&
                candidate.organization_id === row.organization_id &&
                candidate.figure_name !== ''
            );
            const tie = tieLabel(row);
            const stage = stageLabel(row);
            return (
              <Card key={row.slot_id} data-testid="origin-group-card">
                <CardHeader className="space-y-2">
                  <CardTitle className="text-base">
                    {row.organization_id ? (
                      <Link to={`/orgs/${row.organization_id}`} className="hover:underline">
                        {row.organization_name}
                      </Link>
                    ) : (
                      row.organization_name || row.slot_name
                    )}
                  </CardTitle>
                  <div className="flex flex-wrap gap-1">
                    {tie && <Badge variant="outline">{tie}</Badge>}
                    {stage && <Badge variant="outline">{stage}</Badge>}
                    {tier && (
                      <Badge variant={TIER_VARIANT[tier.tier] ?? 'outline'}>
                        {formatTier(tier.tier)}
                      </Badge>
                    )}
                  </div>
                </CardHeader>
                <CardContent className="space-y-2 text-sm">
                  {personRows.map((person) => (
                    <p key={person.slot_id}>
                      <span className="font-medium">{person.figure_name}</span>
                      {person.value && ` · ${person.value}`}
                    </p>
                  ))}
                  {row.choice_name && <p className="font-medium">{row.choice_name}</p>}
                  {row.choice_description && (
                    <p className="text-muted-foreground">{row.choice_description}</p>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
      <p>{background || 'TBD'}</p>
    </section>
  );
}
