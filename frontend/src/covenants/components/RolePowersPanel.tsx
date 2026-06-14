/**
 * RolePowersPanel — read-only display of each active member's passive role power.
 *
 * Reads role_powers from useCovenantPowers and renders one card per membership:
 *   - The covenant role name prominently, plus the bearer (Character #{sheet}).
 *   - When a capability is woven, its name + narrative snippet (italic, muted),
 *     with an "Engaged" badge if the power is live, or a muted "Latent" badge
 *     when it lies dormant until the member engages.
 *   - When no capability is unlocked yet, a muted line noting the (optional)
 *     resonance the role channels but no power.
 *
 * Single-responsibility sibling to RitesPanel: no mutations, no dialogs.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCovenantPowers } from '@/covenants/queries';
import type { RolePower } from '@/covenants/api';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface RolePowersPanelProps {
  covenantId: number;
}

// ---------------------------------------------------------------------------
// Single role-power card
// ---------------------------------------------------------------------------

function RolePowerCard({ power }: { power: RolePower }) {
  const hasCapability = power.capability_name !== null;

  return (
    <Card data-testid="role-power-card">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <CardTitle className="text-base">{power.covenant_role_name}</CardTitle>
            <p className="text-xs text-muted-foreground">Character #{power.character_sheet}</p>
          </div>
          {hasCapability &&
            (power.engaged ? (
              <Badge variant="default" className="text-xs">
                Engaged
              </Badge>
            ) : (
              <Badge variant="secondary" className="text-xs">
                Latent
              </Badge>
            ))}
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        {hasCapability ? (
          <>
            <p className="text-sm font-medium">{power.capability_name}</p>
            {power.narrative_snippet && (
              <p className="text-sm italic text-muted-foreground">{power.narrative_snippet}</p>
            )}
          </>
        ) : (
          <p className="text-sm text-muted-foreground">
            {power.resonance_name
              ? `Channeling ${power.resonance_name} — no power unlocked`
              : 'No role power yet'}
          </p>
        )}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Panel
// ---------------------------------------------------------------------------

export function RolePowersPanel({ covenantId }: RolePowersPanelProps) {
  const { data: powers, isLoading } = useCovenantPowers(covenantId);

  if (isLoading) {
    return null;
  }

  const rolePowers = powers?.role_powers ?? [];

  return (
    <section>
      <h2 className="mb-3 text-lg font-semibold">Role Powers</h2>

      {rolePowers.length === 0 ? (
        <p className="py-4 text-center text-sm text-muted-foreground">No role powers.</p>
      ) : (
        <div className="space-y-3" data-testid="role-powers-list">
          {rolePowers.map((power) => (
            <RolePowerCard key={power.membership_id} power={power} />
          ))}
        </div>
      )}
    </section>
  );
}
