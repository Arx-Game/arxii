/**
 * Trigger-based mission giver editor (#729 Phase 3).
 *
 * Staff surface for the two surviving giver kinds — ROOM_TRIGGER (a room a
 * player enters) and ENVIRONMENTAL_DETAIL (an object a player examines). Each
 * giver holds a flat pool of mission templates; the runtime (Phase 2) draws an
 * eligible one and hands it to the player on entry / examine.
 *
 * The target is entered as an Evennia object id (pk) for now — the server
 * validates that the object's typeclass matches the kind (a Room for
 * ROOM_TRIGGER, a non-Room/Character/Exit Object for ENVIRONMENTAL_DETAIL) and
 * returns a 400 on a mismatch. A typeclass-constrained object picker is a
 * follow-up.
 */
import { Loader2 } from 'lucide-react';
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
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

import { ApiValidationError, flattenErrorMessage } from '../api';
import {
  useCreateGiver,
  useDeleteGiver,
  useGivers,
  useMissionTemplates,
  usePatchGiver,
} from '../queries';
import type { MissionGiver } from '../types';

const KINDS = [
  { value: 'room_trigger', label: 'Room trigger (on enter)' },
  { value: 'environmental_detail', label: 'Environmental detail (on examine)' },
];

function errText(err: unknown, fallback: string): string {
  return err instanceof ApiValidationError ? flattenErrorMessage(err.fieldErrors) : fallback;
}

function numOrNull(raw: string): number | null {
  const t = raw.trim();
  if (t === '') return null;
  const n = Number(t);
  return Number.isFinite(n) ? n : null;
}

export function TriggerGiversPage() {
  const { data, isLoading } = useGivers();
  const givers = data?.results ?? [];

  return (
    <div className="container mx-auto max-w-3xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Trigger Givers</h1>
        <p className="text-sm text-muted-foreground">
          Rooms and objects that hand a player a mission when entered or examined.
        </p>
      </div>

      <CreateGiverCard />

      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : givers.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">No trigger givers yet.</p>
      ) : (
        givers.map((giver) => <GiverCard key={giver.id} giver={giver} />)
      )}
    </div>
  );
}

function CreateGiverCard() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const [kind, setKind] = useState('room_trigger');
  const create = useCreateGiver();

  const submit = () => {
    if (!name.trim()) return;
    create.mutate(
      { name: name.trim(), giver_kind: kind as MissionGiver['giver_kind'] },
      {
        onSuccess: () => {
          setOpen(false);
          setName('');
        },
      }
    );
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        New trigger giver
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">New trigger giver</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label>Name</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} />
          </div>
          <div className="space-y-1">
            <Label>Kind</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>
        {create.isError && (
          <p className="text-sm text-destructive">{errText(create.error, 'Could not create.')}</p>
        )}
        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={!name.trim() || create.isPending}>
            {create.isPending ? 'Creating…' : 'Create'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function GiverCard({ giver }: { giver: MissionGiver }) {
  const patch = usePatchGiver();
  const del = useDeleteGiver();
  const { data: templatesData } = useMissionTemplates({});
  const templates = templatesData?.results ?? [];

  const [kind, setKind] = useState<string>(giver.giver_kind ?? 'room_trigger');
  const [target, setTarget] = useState(giver.target?.toString() ?? '');
  const [org, setOrg] = useState(giver.org?.toString() ?? '');
  const [isActive, setIsActive] = useState(giver.is_active ?? true);
  const [picked, setPicked] = useState<number[]>(giver.templates ?? []);

  useEffect(() => {
    setKind(giver.giver_kind ?? 'room_trigger');
    setTarget(giver.target?.toString() ?? '');
    setOrg(giver.org?.toString() ?? '');
    setIsActive(giver.is_active ?? true);
    setPicked(giver.templates ?? []);
  }, [giver]);

  const toggle = (id: number) =>
    setPicked((cur) => (cur.includes(id) ? cur.filter((x) => x !== id) : [...cur, id]));

  const save = () => {
    patch.mutate({
      id: giver.id,
      body: {
        giver_kind: kind as MissionGiver['giver_kind'],
        target: numOrNull(target),
        org: numOrNull(org),
        is_active: isActive,
        templates: picked,
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between text-base">
          <span>{giver.name}</span>
          {!giver.is_publishable && (
            <span className="text-xs font-normal text-amber-600">needs a target</span>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Kind</Label>
            <Select value={kind} onValueChange={setKind}>
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {KINDS.map((k) => (
                  <SelectItem key={k.value} value={k.value}>
                    {k.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <Switch checked={isActive} onCheckedChange={setIsActive} />
            Active
          </label>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Target object id</Label>
            <Input
              type="number"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              placeholder="Room / object pk"
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs text-muted-foreground">Org id (optional)</Label>
            <Input type="number" value={org} onChange={(e) => setOrg(e.target.value)} />
          </div>
        </div>

        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">Mission pool</Label>
          <div className="max-h-40 space-y-1 overflow-y-auto rounded-md border p-2">
            {templates.length === 0 ? (
              <p className="text-xs text-muted-foreground">No templates available.</p>
            ) : (
              templates.map((t) => (
                <label key={t.id} className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={picked.includes(t.id)}
                    onChange={() => toggle(t.id)}
                  />
                  {t.name}
                </label>
              ))
            )}
          </div>
        </div>

        {patch.isError && (
          <p className="text-sm text-destructive">{errText(patch.error, 'Could not save.')}</p>
        )}
        <div className="flex justify-between">
          <Button size="sm" onClick={save} disabled={patch.isPending}>
            {patch.isPending ? 'Saving…' : 'Save'}
          </Button>
          <Button
            size="sm"
            variant="destructive"
            onClick={() => del.mutate(giver.id)}
            disabled={del.isPending}
          >
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
