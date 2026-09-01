/**
 * RoomAuthoringSections — the #3269 Phase B panel: everything a room carries,
 * visible and editable in one place. Mounted inside the staff RoomDetailPanel
 * under the identity/flags block; reads the room row from the area payload,
 * the pick-lists from `payload.catalogs`, and the heavy per-room data (exit
 * profiles, comfort, ambient rows) from the selection-time room-detail query.
 */
import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';

import { useRoomDetailQuery } from '../queries';
import type { WorldBuilderAreaManager, WorldBuilderRoom } from '../types';

interface RoomAuthoringSectionsProps {
  room: WorldBuilderRoom;
  catalogs: WorldBuilderAreaManager['catalogs'];
  runAction: (key: string, kwargs: Record<string, unknown>) => void;
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-md border p-2">
      <h4 className="text-sm font-semibold">{title}</h4>
      {children}
    </div>
  );
}

export function StatsSection({ room, runAction }: Omit<RoomAuthoringSectionsProps, 'catalogs'>) {
  const [statKey, setStatKey] = useState('');
  const [value, setValue] = useState('');
  const touched = room.stats.filter(
    (s) => s.authored !== null || s.pinned !== null || s.effective !== s.default
  );
  return (
    <Section title="Ambient stats">
      {touched.length > 0 && (
        <div className="flex flex-col gap-0.5 text-xs">
          {touched.map((s) => (
            <div key={s.key} className="flex items-center gap-1">
              <span className="w-28 text-muted-foreground">{s.label}</span>
              <span>{s.effective}</span>
              {s.authored !== null && <Badge variant="outline">authored {s.authored}</Badge>}
              {s.pinned !== null && <Badge variant="destructive">pinned {s.pinned}</Badge>}
            </div>
          ))}
        </div>
      )}
      <div className="flex items-end gap-1">
        <div className="flex flex-1 flex-col gap-1">
          <Label className="text-xs">Stat</Label>
          <Select value={statKey} onValueChange={setStatKey}>
            <SelectTrigger className="h-8">
              <SelectValue placeholder="Pick a stat" />
            </SelectTrigger>
            <SelectContent>
              {room.stats.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Input
          className="h-8 w-20"
          type="number"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="value"
        />
      </div>
      <div className="flex gap-1">
        <Button
          size="sm"
          disabled={!statKey || value === ''}
          onClick={() =>
            runAction('staff_set_room_stat', {
              room_id: room.id,
              stat_key: statKey,
              value: Number(value),
            })
          }
        >
          Author
        </Button>
        <Button
          size="sm"
          variant="outline"
          disabled={!statKey || value === ''}
          title="Pin cuts the whole cascade for this stat — weather/traffic no longer reach it"
          onClick={() =>
            runAction('staff_set_room_stat', {
              room_id: room.id,
              stat_key: statKey,
              value: Number(value),
              pin: true,
            })
          }
        >
          Pin
        </Button>
        <Button
          size="sm"
          variant="ghost"
          disabled={!statKey}
          onClick={() =>
            runAction('staff_set_room_stat', { room_id: room.id, stat_key: statKey, clear: true })
          }
        >
          Clear
        </Button>
      </div>
    </Section>
  );
}

export function PlacesSection({ room, runAction }: Omit<RoomAuthoringSectionsProps, 'catalogs'>) {
  const [name, setName] = useState('');
  return (
    <Section title={`Places (${room.places.length})`}>
      {room.places.map((place) => (
        <div key={place.id} className="flex items-center gap-1 text-sm">
          <span className="flex-1">{place.name}</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_place', { place_id: place.id })}
          >
            Remove
          </Button>
        </div>
      ))}
      <div className="flex gap-1">
        <Input
          className="h-8"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="the bar, corner booth…"
        />
        <Button
          size="sm"
          disabled={!name.trim()}
          onClick={() => {
            runAction('staff_add_place', { room_id: room.id, name: name.trim() });
            setName('');
          }}
        >
          Add
        </Button>
      </div>
    </Section>
  );
}

/** Mirrors `world.narrative.constants.ConditionType` — the ambience door's add-condition menu. */
const AMBIENT_CONDITION_TYPES: { value: string; label: string }[] = [
  { value: 'species', label: 'Species' },
  { value: 'resonance_min', label: 'Resonance threshold' },
  { value: 'distinction', label: 'Distinction' },
  { value: 'renown_min', label: 'Fame tier' },
  { value: 'legend_deed', label: 'Has legend deeds' },
];

function LineConditions({
  line,
  catalogs,
  runAction,
}: {
  line: { id: number; conditions: { id: number; condition_type: string; label: string }[] };
  catalogs: WorldBuilderAreaManager['catalogs'];
  runAction: RoomAuthoringSectionsProps['runAction'];
}) {
  return (
    <div className="ml-2 flex flex-col gap-1" data-testid={`line-conditions-${line.id}`}>
      <div className="flex flex-wrap gap-1">
        {line.conditions.map((condition) => (
          <Badge key={condition.id} variant="outline" className="gap-1 text-[0.65rem]">
            {condition.label}
            <button
              type="button"
              aria-label={`remove condition: ${condition.label}`}
              onClick={() =>
                runAction('staff_remove_ambient_condition', {
                  condition_id: condition.id,
                  line_id: line.id,
                })
              }
            >
              ✕
            </button>
          </Badge>
        ))}
      </div>
      <AddConditionRow lineId={line.id} catalogs={catalogs} runAction={runAction} />
    </div>
  );
}

function AddConditionRow({
  lineId,
  catalogs,
  runAction,
}: {
  lineId: number;
  catalogs: WorldBuilderAreaManager['catalogs'];
  runAction: RoomAuthoringSectionsProps['runAction'];
}) {
  const [conditionType, setConditionType] = useState('');
  const [targetId, setTargetId] = useState('');
  const [minimumValue, setMinimumValue] = useState('1');
  const [fameTier, setFameTier] = useState('');

  const refOptions =
    conditionType === 'species'
      ? catalogs.species
      : conditionType === 'resonance_min'
        ? catalogs.resonances
        : conditionType === 'distinction'
          ? catalogs.distinctions
          : [];
  const needsRef = refOptions.length > 0 || conditionType === 'renown_min';
  const canAdd =
    conditionType !== '' &&
    (conditionType === 'legend_deed' ||
      (conditionType === 'renown_min' ? fameTier !== '' : targetId !== ''));

  const submit = () => {
    const kwargs: Record<string, unknown> = { line_id: lineId, condition_type: conditionType };
    if (targetId) kwargs.target_id = Number(targetId);
    if (conditionType === 'resonance_min') kwargs.minimum_value = Number(minimumValue);
    if (conditionType === 'renown_min') kwargs.min_fame_tier = fameTier;
    runAction('staff_add_ambient_condition', kwargs);
    setConditionType('');
    setTargetId('');
    setFameTier('');
  };

  return (
    <div className="flex flex-wrap items-center gap-1">
      <Select value={conditionType} onValueChange={setConditionType}>
        <SelectTrigger className="h-7 w-40 text-xs" data-testid={`condition-type-${lineId}`}>
          <SelectValue placeholder="⊕ gate this line…" />
        </SelectTrigger>
        <SelectContent>
          {AMBIENT_CONDITION_TYPES.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {needsRef && conditionType !== 'renown_min' && (
        <Select value={targetId} onValueChange={setTargetId}>
          <SelectTrigger className="h-7 w-40 text-xs" data-testid={`condition-ref-${lineId}`}>
            <SelectValue placeholder="which…" />
          </SelectTrigger>
          <SelectContent>
            {refOptions.map((option) => (
              <SelectItem key={option.id} value={String(option.id)}>
                {option.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {conditionType === 'resonance_min' && (
        <Input
          className="h-7 w-16 text-xs"
          type="number"
          min={1}
          value={minimumValue}
          onChange={(event) => setMinimumValue(event.target.value)}
          aria-label="minimum resonance"
        />
      )}
      {conditionType === 'renown_min' && (
        <Select value={fameTier} onValueChange={setFameTier}>
          <SelectTrigger className="h-7 w-40 text-xs" data-testid={`condition-tier-${lineId}`}>
            <SelectValue placeholder="at least…" />
          </SelectTrigger>
          <SelectContent>
            {catalogs.fame_tiers.map((tier) => (
              <SelectItem key={tier.value} value={tier.value}>
                {tier.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {conditionType !== '' && (
        <Button size="sm" className="h-7" disabled={!canAdd} onClick={submit}>
          Add
        </Button>
      )}
    </div>
  );
}

export function AtmosphereSection({ room, catalogs, runAction }: RoomAuthoringSectionsProps) {
  const { data: detail } = useRoomDetailQuery(room.id);
  const [lineText, setLineText] = useState('');
  const [emitText, setEmitText] = useState('');
  const [gateStat, setGateStat] = useState('');
  const [gateMin, setGateMin] = useState('');
  return (
    <Section
      title={`Atmosphere (${room.ambient_counts.lines} entry / ${room.ambient_counts.emits} linger)`}
    >
      {(detail?.ambient_lines ?? []).map((line) => (
        <div key={line.id} className="flex flex-col gap-1">
          <div className="flex items-start gap-1 text-xs">
            <span className="flex-1">{line.arriver_body || line.bystander_body}</span>
            <Button
              size="sm"
              variant="ghost"
              onClick={() => runAction('staff_remove_ambient_line', { line_id: line.id })}
            >
              Remove
            </Button>
          </div>
          <LineConditions line={line} catalogs={catalogs} runAction={runAction} />
        </div>
      ))}
      <div className="flex gap-1">
        <Textarea
          rows={2}
          value={lineText}
          onChange={(e) => setLineText(e.target.value)}
          placeholder="Entry line (shown to the arriver)…"
        />
        <Button
          size="sm"
          disabled={!lineText.trim()}
          onClick={() => {
            runAction('staff_add_ambient_line', {
              room_id: room.id,
              arriver_body: lineText.trim(),
            });
            setLineText('');
          }}
        >
          Add line
        </Button>
      </div>
      {(detail?.ambient_emits ?? []).map((emit) => (
        <div key={emit.id} className="flex items-start gap-1 text-xs">
          <span className="flex-1">
            {emit.text}
            {emit.gate_stat_key && (
              <Badge variant="outline" className="ml-1">
                {emit.gate_stat_key} ≥ {emit.gate_min}
              </Badge>
            )}
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_ambient_emit', { emit_id: emit.id })}
          >
            Remove
          </Button>
        </div>
      ))}
      <div className="flex flex-col gap-1">
        <Textarea
          rows={2}
          value={emitText}
          onChange={(e) => setEmitText(e.target.value)}
          placeholder="Linger line (fires while occupants remain)…"
        />
        <div className="flex gap-1">
          <Select value={gateStat} onValueChange={setGateStat}>
            <SelectTrigger className="h-8 flex-1">
              <SelectValue placeholder="Gate stat (optional)" />
            </SelectTrigger>
            <SelectContent>
              {room.stats.map((s) => (
                <SelectItem key={s.key} value={s.key}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            className="h-8 w-20"
            type="number"
            value={gateMin}
            onChange={(e) => setGateMin(e.target.value)}
            placeholder="min"
          />
          <Button
            size="sm"
            disabled={!emitText.trim()}
            onClick={() => {
              runAction('staff_add_ambient_emit', {
                room_id: room.id,
                text: emitText.trim(),
                gate_stat_key: gateStat || undefined,
                gate_min: gateMin === '' ? undefined : Number(gateMin),
              });
              setEmitText('');
            }}
          >
            Add linger
          </Button>
        </div>
      </div>
    </Section>
  );
}

export function FeatureSection({ room, catalogs, runAction }: RoomAuthoringSectionsProps) {
  const [kind, setKind] = useState('');
  return (
    <Section title="Feature">
      {room.feature ? (
        <div className="flex items-center gap-1 text-sm">
          <span className="flex-1">
            {room.feature.kind} (level {room.feature.level})
          </span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_room_feature', { room_id: room.id })}
          >
            Dissolve
          </Button>
        </div>
      ) : (
        <div className="flex gap-1">
          <Select value={kind} onValueChange={setKind}>
            <SelectTrigger className="h-8 flex-1">
              <SelectValue placeholder="Install a feature…" />
            </SelectTrigger>
            <SelectContent>
              {catalogs.feature_kinds.map((name) => (
                <SelectItem key={name} value={name}>
                  {name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Button
            size="sm"
            disabled={!kind}
            onClick={() => runAction('staff_install_room_feature', { room_id: room.id, kind })}
          >
            Install
          </Button>
        </div>
      )}
    </Section>
  );
}

export function StaffingSection({ room, catalogs, runAction }: RoomAuthoringSectionsProps) {
  const [role, setRole] = useState('');
  return (
    <Section title={`Staffing (${room.functionaries.length})`}>
      {room.functionaries.map((name) => (
        <div key={name} className="flex items-center gap-1 text-sm">
          <span className="flex-1">{name}</span>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => runAction('staff_remove_functionary', { room_id: room.id, role: name })}
          >
            Remove
          </Button>
        </div>
      ))}
      <div className="flex gap-1">
        <Select value={role} onValueChange={setRole}>
          <SelectTrigger className="h-8 flex-1">
            <SelectValue placeholder="Assign a role…" />
          </SelectTrigger>
          <SelectContent>
            {catalogs.npc_roles.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          disabled={!role}
          onClick={() => runAction('staff_assign_functionary', { room_id: room.id, role })}
        >
          Assign
        </Button>
      </div>
    </Section>
  );
}

function StageTravelSection({ room, catalogs, runAction }: RoomAuthoringSectionsProps) {
  const [blueprint, setBlueprint] = useState(room.default_blueprint ?? '');
  return (
    <Section title="Stage & travel">
      <div className="flex items-center gap-1">
        <Label className="w-24 text-xs">Blueprint</Label>
        <Select value={blueprint} onValueChange={setBlueprint}>
          <SelectTrigger className="h-8 flex-1">
            <SelectValue placeholder="none" />
          </SelectTrigger>
          <SelectContent>
            {catalogs.blueprints.map((name) => (
              <SelectItem key={name} value={name}>
                {name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          onClick={() => runAction('staff_set_room_blueprint', { room_id: room.id, blueprint })}
        >
          Set
        </Button>
        <Button
          size="sm"
          variant="ghost"
          onClick={() => {
            setBlueprint('');
            runAction('staff_set_room_blueprint', { room_id: room.id, blueprint: '' });
          }}
        >
          Clear
        </Button>
      </div>
      <div className="flex items-center gap-2">
        <Label className="w-24 text-xs">Travel hub</Label>
        <Switch
          checked={room.travel_hub != null}
          onCheckedChange={(checked) =>
            runAction('staff_set_travel_hub', {
              room_id: room.id,
              enabled: checked,
              modes: 'land',
            })
          }
        />
        {room.travel_hub && (
          <span className="text-xs text-muted-foreground">
            {room.travel_hub.name} ({room.travel_hub.travel_modes.join(', ')}) — routes are authored
            separately
          </span>
        )}
      </div>
    </Section>
  );
}

function BindingsSection({ room, catalogs, runAction }: RoomAuthoringSectionsProps) {
  const [startingAreaId, setStartingAreaId] = useState('');
  return (
    <Section title="Starting bindings">
      {room.starting_bindings.map((label) => (
        <p key={label} className="text-xs">
          {label}
        </p>
      ))}
      <div className="flex gap-1">
        <Select value={startingAreaId} onValueChange={setStartingAreaId}>
          <SelectTrigger className="h-8 flex-1">
            <SelectValue placeholder="Bind to starting area…" />
          </SelectTrigger>
          <SelectContent>
            {catalogs.starting_areas.map((sa) => (
              <SelectItem key={sa.id} value={String(sa.id)}>
                {sa.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button
          size="sm"
          disabled={!startingAreaId}
          onClick={() =>
            runAction('staff_set_starting_room', {
              room_id: room.id,
              starting_area_id: Number(startingAreaId),
            })
          }
        >
          Bind
        </Button>
      </div>
    </Section>
  );
}

function ExitDetailSection({ room, runAction }: Omit<RoomAuthoringSectionsProps, 'catalogs'>) {
  const { data: detail } = useRoomDetailQuery(room.id);
  if (!detail?.exits.length) return null;
  return (
    <Section title="Exit detail">
      {detail.exits.map((exit) => (
        <div key={exit.id} className="flex items-center gap-1 text-xs">
          <span className="w-20">{exit.name}</span>
          <Select
            value={exit.kind}
            onValueChange={(kind) => runAction('staff_set_exit_detail', { exit_id: exit.id, kind })}
          >
            <SelectTrigger className="h-7 w-28">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="door">Door</SelectItem>
              <SelectItem value="window">Window</SelectItem>
            </SelectContent>
          </Select>
          {exit.kind === 'window' && (
            <Switch
              checked={exit.is_open}
              onCheckedChange={(is_open) =>
                runAction('staff_set_exit_detail', { exit_id: exit.id, is_open })
              }
            />
          )}
          <span className="flex-1 truncate text-muted-foreground">{exit.aliases.join(', ')}</span>
        </div>
      ))}
    </Section>
  );
}

function ComfortSection({ room }: { room: WorldBuilderRoom }) {
  const { data: detail } = useRoomDetailQuery(room.id);
  if (!detail) return null;
  const biting = detail.comfort.axes.filter((axis) => axis.net > 0);
  return (
    <Section title={`Comfort (level ${detail.comfort.level})`}>
      {biting.length === 0 ? (
        <p className="text-xs text-muted-foreground">Nothing bites here.</p>
      ) : (
        biting.map((axis) => (
          <p key={axis.key} className="text-xs">
            {axis.key}: {axis.pressure} − {axis.mitigation} = {axis.net}
            {axis.sheltered && ' (sheltered)'}
          </p>
        ))
      )}
    </Section>
  );
}

export function RoomAuthoringSections(props: RoomAuthoringSectionsProps) {
  return (
    <div className="flex flex-col gap-2" data-testid="room-authoring-sections">
      <StatsSection room={props.room} runAction={props.runAction} />
      <PlacesSection room={props.room} runAction={props.runAction} />
      <AtmosphereSection {...props} />
      <FeatureSection {...props} />
      <StaffingSection {...props} />
      <StageTravelSection {...props} />
      <BindingsSection {...props} />
      <ExitDetailSection room={props.room} runAction={props.runAction} />
      <ComfortSection room={props.room} />
    </div>
  );
}
