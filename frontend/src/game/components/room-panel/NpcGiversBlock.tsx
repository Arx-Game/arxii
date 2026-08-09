/**
 * NpcGiversBlock (#3044) — "Talk" affordance for NPC service givers standing
 * in the current room.
 *
 * An interactable NPC in this world is a `Functionary` placement
 * (`world.npc_services.models.Functionary`) — a class-1+ NPC role posted to a
 * room. A Functionary carries NO ObjectDB of its own (it's a faceless
 * room-anchored slot, not a physical object), so it can never appear in the
 * room's `characters`/`objects` lists — the room-state payload surfaces it
 * separately as `npc_givers`. Mounts the same `NPCInteractionDialog` the
 * OrgBooks "summon" flow uses (no fork) — reuses its whole start/resolve/end
 * interaction loop, just a different entry point.
 */
import { useState } from 'react';
import { MessageCircle } from 'lucide-react';

import type { NpcGiver } from '@/hooks/types';
import { Button } from '@/components/ui/button';
import { NPCInteractionDialog } from '@/npc_services/components/NPCInteractionDialog';

interface NpcGiversBlockProps {
  npcGivers: NpcGiver[];
}

export function NpcGiversBlock({ npcGivers }: NpcGiversBlockProps) {
  const [talkingTo, setTalkingTo] = useState<NpcGiver | null>(null);

  if (npcGivers.length === 0) {
    return null;
  }

  return (
    <div className="border-b px-3 py-2" data-testid="npc-givers-block">
      <div className="mb-1 flex items-center gap-1 text-xs font-semibold uppercase text-muted-foreground">
        <MessageCircle className="h-3 w-3" />
        People here
      </div>
      <ul className="space-y-1">
        {npcGivers.map((giver) => (
          <li key={giver.role_id} className="flex items-center justify-between gap-2 text-xs">
            <span>{giver.name}</span>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-6 shrink-0 px-2 text-xs"
              onClick={() => setTalkingTo(giver)}
              data-testid={`talk-${giver.role_id}`}
            >
              Talk
            </Button>
          </li>
        ))}
      </ul>
      {talkingTo ? (
        <NPCInteractionDialog
          roleId={talkingTo.role_id}
          title={talkingTo.name}
          open
          onOpenChange={(next) => {
            if (!next) setTalkingTo(null);
          }}
        />
      ) : null}
    </div>
  );
}
