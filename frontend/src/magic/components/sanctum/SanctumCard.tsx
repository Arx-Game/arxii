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

export function SanctumCard({ sanctum }: SanctumCardProps) {
  const [homecomingOpen, setHomecomingOpen] = useState(false);
  const [weaveOpen, setWeaveOpen] = useState(false);

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
      </CardContent>
      <CardFooter className="gap-2">
        <Button size="sm" onClick={() => setHomecomingOpen(true)}>
          Homecoming
        </Button>
        <Button size="sm" variant="outline" onClick={() => setWeaveOpen(true)}>
          Weave thread
        </Button>
      </CardFooter>
      <HomecomingDialog sanctum={sanctum} open={homecomingOpen} onOpenChange={setHomecomingOpen} />
      <WeaveDialog sanctum={sanctum} open={weaveOpen} onOpenChange={setWeaveOpen} />
    </Card>
  );
}
