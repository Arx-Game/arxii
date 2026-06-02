/**
 * SanctumCard — single Sanctum tile on the dashboard.
 *
 * Surfaces the key state (resonance type, level, current Homecoming reservoir,
 * last ritual timestamps, overflow escrow) and the two primary actions every
 * weaver/owner has: Ritual of Homecoming and Weave thread.
 */

import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';

import type { SanctumDetails } from '../../sanctumTypes';

import { useAbsorb } from '../../sanctumQueries';

import { HomecomingDialog } from './HomecomingDialog';
import { WeaveDialog } from './WeaveDialog';

export interface SanctumCardProps {
  sanctum: SanctumDetails;
}

function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return 'Never';
  const dt = new Date(iso);
  if (Number.isNaN(dt.getTime())) return 'Never';
  return dt.toLocaleString();
}

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to absorb from this Sanctum';
}

export function SanctumCard({ sanctum }: Readonly<SanctumCardProps>) {
  const [homecomingOpen, setHomecomingOpen] = useState(false);
  const [weaveOpen, setWeaveOpen] = useState(false);
  const absorb = useAbsorb(sanctum.feature_instance_id);
  const pendingWeaving = sanctum.pending_weaving;
  const pendingOwnerBonus = sanctum.pending_owner_bonus;
  const pendingTotal = pendingWeaving + pendingOwnerBonus;
  let absorbButtonLabel: string;
  if (absorb.isPending) {
    absorbButtonLabel = 'Absorbing…';
  } else if (pendingTotal > 0) {
    absorbButtonLabel = `Absorb (${pendingTotal})`;
  } else {
    absorbButtonLabel = 'Absorb';
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-2">
          <div>
            <CardTitle>{sanctum.resonance_type_name} Sanctum</CardTitle>
            <CardDescription>Room #{sanctum.room_profile_id}</CardDescription>
          </div>
          <Badge variant={sanctum.owner_mode === 'COVENANT' ? 'default' : 'secondary'}>
            {sanctum.owner_mode === 'COVENANT' ? 'Covenant' : 'Personal'}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-sm">
        <div className="flex justify-between">
          <span className="text-muted-foreground">Level</span>
          <span className="font-medium">{sanctum.level}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Imbued reservoir</span>
          <span className="font-medium">{sanctum.homecoming_sum}</span>
        </div>
        {Number(sanctum.pending_sacrifice_overflow) > 0 ? (
          <div className="flex justify-between">
            <span className="text-muted-foreground">Pending escrow</span>
            <span className="font-medium">{sanctum.pending_sacrifice_overflow}</span>
          </div>
        ) : null}
        <div className="flex justify-between">
          <span className="text-muted-foreground">Last Homecoming</span>
          <span>{formatTimestamp(sanctum.last_homecoming_ritual_at)}</span>
        </div>
        <div className="flex justify-between">
          <span className="text-muted-foreground">Last Purging</span>
          <span>{formatTimestamp(sanctum.last_purging_ritual_at)}</span>
        </div>
        {pendingTotal > 0 ? (
          <div className="mt-2 rounded-md bg-muted/40 p-2 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Well — your gift</span>
              <span className="font-medium">{pendingTotal}</span>
            </div>
            {pendingOwnerBonus > 0 ? (
              <div className="text-xs text-muted-foreground">
                ({pendingWeaving} weaving + {pendingOwnerBonus} bonus)
              </div>
            ) : null}
            <p className="mt-1 text-xs text-muted-foreground">
              Visit the Sanctum room to absorb its gathered resonance.
            </p>
          </div>
        ) : null}
        {absorb.isError ? (
          <p className="text-sm text-destructive">{extractErrorMessage(absorb.error)}</p>
        ) : null}
      </CardContent>
      <CardFooter className="flex-wrap gap-2">
        <Button size="sm" onClick={() => setHomecomingOpen(true)}>
          Homecoming
        </Button>
        <Button size="sm" variant="outline" onClick={() => setWeaveOpen(true)}>
          Weave thread
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={pendingTotal === 0 || absorb.isPending}
          onClick={() => absorb.mutate()}
        >
          {absorbButtonLabel}
        </Button>
      </CardFooter>
      <HomecomingDialog sanctum={sanctum} open={homecomingOpen} onOpenChange={setHomecomingOpen} />
      <WeaveDialog sanctum={sanctum} open={weaveOpen} onOpenChange={setWeaveOpen} />
    </Card>
  );
}
