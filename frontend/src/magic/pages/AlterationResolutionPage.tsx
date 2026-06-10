/**
 * AlterationResolutionPage — /magic/alterations (#877).
 *
 * Lists the account's OPEN pending alterations (Mage Scars) and opens
 * AlterationResolveDialog for each. This is the release valve for the
 * XP-spend gate (AlterationGateError).
 */

import { useState } from 'react';
import { usePendingAlterations } from '../queries';
import { getTierCaps } from '../types';
import type { PendingAlteration } from '../types';
import { AlterationResolveDialog } from '../components/alterations/AlterationResolveDialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export default function AlterationResolutionPage() {
  const { data, isLoading, isError } = usePendingAlterations();
  const [resolving, setResolving] = useState<PendingAlteration | null>(null);
  const pendings = data?.results ?? [];

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Mage Scars</h1>
        <p className="text-muted-foreground">
          Overburned magic leaves its mark. Each unresolved scar locks that character&apos;s XP
          spending until you decide what shape it takes.
        </p>
      </div>

      {isLoading && <Skeleton className="h-32 w-full" />}

      {isError && (
        <Card>
          <CardContent className="py-8 text-center text-destructive" role="alert">
            Could not load your pending alterations — the gate may still be active. Try again
            shortly.
          </CardContent>
        </Card>
      )}

      {!isLoading && !isError && pendings.length === 0 && (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            No unresolved alterations. Your flesh is your own — for now.
          </CardContent>
        </Card>
      )}

      {pendings.map((pending) => {
        const caps = getTierCaps(pending);
        return (
          <Card key={pending.id}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Badge variant="destructive">Tier {pending.tier}</Badge>
                {pending.tier_display} Mage Scar
              </CardTitle>
              <CardDescription>
                {pending.character_name} — marked by {pending.origin_affinity_name} magic (
                {pending.origin_resonance_name}) on {formatDate(pending.created_at)}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                Caps for this tier: social {caps.social_cap}, weakness {caps.weakness_cap},
                resonance {caps.resonance_cap}
                {caps.visibility_required ? ' — always visible' : ''}
              </p>
              <Button onClick={() => setResolving(pending)}>Resolve</Button>
            </CardContent>
          </Card>
        );
      })}

      {resolving && (
        <AlterationResolveDialog
          pending={resolving}
          open
          onOpenChange={(open) => {
            if (!open) setResolving(null);
          }}
        />
      )}
    </div>
  );
}
