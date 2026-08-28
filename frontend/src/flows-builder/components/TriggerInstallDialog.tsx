/**
 * TriggerInstallDialog — install a TriggerDefinition on a specific game
 * object, creating a `Trigger` row (#3417 task 12).
 *
 * Opened from the Installed Triggers tab (trigger-definition picker shown)
 * and from a TriggerDefinition's own editor page (`fixedTriggerDefinitionId`
 * locks that picker to the current row instead).
 *
 * The object picker reuses `world-builder`'s cross-area room search
 * (`useRoomSearchQuery` / `WorldBuilderRoomHit`, `world-builder/queries.ts`
 * + `types.ts`) rather than inventing a second one — a `Trigger.obj` is
 * most often a room, and that hook already exists for exactly this
 * "search rooms by name across the whole grid" need. A raw numeric
 * "Object id" input sits alongside it as the escape hatch for the
 * non-room case (a trigger can attach to any `ObjectDB`, per the model's
 * `obj` FK) — both write into the same `objIdText` state, so picking a
 * room from the combobox just fills the id field.
 *
 * `source_condition`/`source_stage` are kept as bare numeric ids for this
 * v1 (staff-only surface, per the task brief) rather than adding condition-
 * instance/stage pickers — `Trigger.clean()` (`flows/models/triggers.py`)
 * cross-checks that a given `source_stage` belongs to `source_condition`'s
 * `ConditionTemplate` and surfaces that as a field error on save.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Combobox, type ComboboxItem } from '@/components/ui/combobox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { flattenErrorMessage } from '@/missions/api';
import { useRoomSearchQuery } from '@/world-builder/queries';

import { ApiValidationError } from '../api';
import { useCreateTrigger, useTriggerDefinitions } from '../queries';

interface TriggerInstallDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Locks the trigger-definition picker when opened from that definition's own page. */
  fixedTriggerDefinitionId?: number;
}

export function TriggerInstallDialog({
  open,
  onOpenChange,
  fixedTriggerDefinitionId,
}: TriggerInstallDialogProps) {
  const [triggerDefinitionId, setTriggerDefinitionId] = useState('');
  const [objIdText, setObjIdText] = useState('');
  const [roomSearchTerm, setRoomSearchTerm] = useState('');
  const [sourceConditionText, setSourceConditionText] = useState('');
  const [sourceStageText, setSourceStageText] = useState('');

  const triggerDefinitionsQuery = useTriggerDefinitions();
  const roomSearchQuery = useRoomSearchQuery(roomSearchTerm);
  const createTrigger = useCreateTrigger();

  const tdItems: ComboboxItem[] = (triggerDefinitionsQuery.data?.results ?? []).map((td) => ({
    value: String(td.id),
    label: td.name,
    secondaryText: td.event_name,
  }));
  const roomItems: ComboboxItem[] = (roomSearchQuery.data ?? []).map((room) => ({
    value: String(room.id),
    label: room.area_name ? `${room.name} (${room.area_name})` : room.name,
  }));

  const effectiveTdId =
    fixedTriggerDefinitionId !== undefined ? String(fixedTriggerDefinitionId) : triggerDefinitionId;

  const reset = () => {
    setTriggerDefinitionId('');
    setObjIdText('');
    setRoomSearchTerm('');
    setSourceConditionText('');
    setSourceStageText('');
  };

  const canSubmit = effectiveTdId !== '' && objIdText.trim() !== '';

  const submit = () => {
    if (!canSubmit) return;
    createTrigger.mutate(
      {
        trigger_definition: Number(effectiveTdId),
        obj: Number(objIdText),
        source_condition: sourceConditionText.trim() ? Number(sourceConditionText) : null,
        source_stage: sourceStageText.trim() ? Number(sourceStageText) : null,
      },
      {
        onSuccess: () => {
          reset();
          onOpenChange(false);
        },
      }
    );
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        if (!next) reset();
        onOpenChange(next);
      }}
    >
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Install a trigger</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-3">
          {fixedTriggerDefinitionId === undefined ? (
            <div className="space-y-1">
              <Label>Trigger definition</Label>
              <Combobox
                items={tdItems}
                value={triggerDefinitionId}
                onValueChange={setTriggerDefinitionId}
                placeholder="Pick a trigger definition…"
              />
            </div>
          ) : null}
          <div className="space-y-1">
            <Label>Search rooms</Label>
            <Input
              value={roomSearchTerm}
              onChange={(e) => setRoomSearchTerm(e.target.value)}
              placeholder="Search rooms by name…"
            />
            <Combobox
              items={roomItems}
              value={objIdText}
              onValueChange={setObjIdText}
              placeholder="Pick a room…"
              emptyMessage={
                roomSearchTerm.trim().length < 2
                  ? 'Type at least 2 characters to search…'
                  : 'No matching rooms.'
              }
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="trigger-install-obj-id">Object id</Label>
            <Input
              id="trigger-install-obj-id"
              type="number"
              value={objIdText}
              onChange={(e) => setObjIdText(e.target.value)}
              placeholder="or type any object's id…"
            />
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="trigger-install-source-condition">Source condition id</Label>
              <Input
                id="trigger-install-source-condition"
                type="number"
                value={sourceConditionText}
                onChange={(e) => setSourceConditionText(e.target.value)}
                placeholder="optional"
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="trigger-install-source-stage">Source stage id</Label>
              <Input
                id="trigger-install-source-stage"
                type="number"
                value={sourceStageText}
                onChange={(e) => setSourceStageText(e.target.value)}
                placeholder="optional"
              />
            </div>
          </div>
          <p className="text-xs text-muted-foreground">
            If both source ids are given, the stage must belong to the source condition's template —
            the server rejects a mismatch.
          </p>
          {createTrigger.isError ? (
            <p className="text-sm text-destructive">
              {createTrigger.error instanceof ApiValidationError
                ? flattenErrorMessage(createTrigger.error.fieldErrors)
                : 'Could not install the trigger.'}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={submit} disabled={!canSubmit || createTrigger.isPending}>
            {createTrigger.isPending ? 'Installing…' : 'Install trigger'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
