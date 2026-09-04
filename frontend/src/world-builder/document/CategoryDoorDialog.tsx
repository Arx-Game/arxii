/**
 * CategoryDoorDialog (#3534) — what a marginalia category header opens: that
 * system's own editor, in a dialog over the manuscript. Per Dan's ruling
 * ("every marginalia category is a door, not a label"), and per
 * anti-reinvention the editors are the reused #3269 Phase B sections
 * (`RoomAuthoringSections`), which already carry the real actions, honest
 * refusals, and their own detail queries — this file only chooses which
 * section(s) a door reveals. The one door with no prior editor is Secrets &
 * Story: its body lists placed clues/triggers with removes and reuses
 * `PlaceClueDialog` for adds.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog';

import { PlaceClueDialog } from '../components/PlaceClueDialog';
import {
  AtmosphereSection,
  FeatureSection,
  PlacesSection,
  StaffingSection,
  StatsSection,
} from '../components/RoomAuthoringSections';
import type { WorldBuilderAreaManager, WorldBuilderRoom } from '../types';
import type { MarginaliaDoor } from './Marginalia';

const DOOR_TITLES: Record<MarginaliaDoor, string> = {
  ambience: 'Ambience',
  people: 'People',
  places: 'Places & Things',
  law: 'Law & Danger',
  secrets: 'Secrets & Story',
};

export interface CategoryDoorDialogProps {
  door: MarginaliaDoor | null;
  onClose: () => void;
  room: WorldBuilderRoom;
  catalogs: WorldBuilderAreaManager['catalogs'];
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

function SecretsDoor({
  room,
  runAction,
}: {
  room: WorldBuilderRoom;
  runAction: CategoryDoorDialogProps['runAction'];
}) {
  const [placeOpen, setPlaceOpen] = useState(false);
  return (
    <div className="flex flex-col gap-2">
      {room.clues.map((placed) => (
        <div key={`clue-${placed.id}`} className="flex items-center gap-2 text-sm">
          <span className="flex-1">
            {placed.clue_name} · search vs {placed.detect_difficulty}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_clue', { room_clue_id: placed.id })}
          >
            Remove
          </Button>
        </div>
      ))}
      {room.clue_triggers.map((trigger) => (
        <div key={`trigger-${trigger.id}`} className="flex items-center gap-2 text-sm">
          <span className="flex-1">{trigger.clue_name} · on entry</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_clue_trigger', { clue_trigger_id: trigger.id })}
          >
            Remove
          </Button>
        </div>
      ))}
      {room.clues.length === 0 && room.clue_triggers.length === 0 && (
        <p className="font-body text-sm italic text-muted-foreground">Nothing hidden here yet.</p>
      )}
      <Button
        size="sm"
        className="self-start"
        onClick={() => setPlaceOpen(true)}
        data-testid="secrets-place-clue"
      >
        ⊕ hide a clue…
      </Button>
      <PlaceClueDialog
        roomId={room.id}
        open={placeOpen}
        onOpenChange={setPlaceOpen}
        runAction={runAction}
      />
    </div>
  );
}

export function CategoryDoorDialog({
  door,
  onClose,
  room,
  catalogs,
  runAction,
}: CategoryDoorDialogProps) {
  return (
    <Dialog open={door != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[80vh] max-w-2xl overflow-y-auto">
        {door != null && (
          <>
            <DialogTitle>
              {DOOR_TITLES[door]} — {room.name}
            </DialogTitle>
            <div data-testid={`door-body-${door}`}>
              {door === 'ambience' && (
                <AtmosphereSection room={room} catalogs={catalogs} runAction={runAction} />
              )}
              {door === 'people' && (
                <StaffingSection room={room} catalogs={catalogs} runAction={runAction} />
              )}
              {door === 'places' && (
                <div className="flex flex-col gap-2">
                  <PlacesSection room={room} runAction={runAction} />
                  <FeatureSection room={room} catalogs={catalogs} runAction={runAction} />
                </div>
              )}
              {door === 'law' && <StatsSection room={room} runAction={runAction} />}
              {door === 'secrets' && <SecretsDoor room={room} runAction={runAction} />}
            </div>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
