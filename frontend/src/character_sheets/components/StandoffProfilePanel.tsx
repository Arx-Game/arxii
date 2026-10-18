/**
 * Standoff profile panel (#4441) — owner-only sheet section.
 *
 * A player gives their own character drives and a cause, picked from the same catalogs
 * creature templates use, and chooses whether other player characters may read and press
 * them in a standoff. Reads GET /standoff-profile/ and writes POST /standoff-profile/, one
 * change per call. While the character stands in a standoff the profile is locked.
 */

import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Subheading } from '@/character_sheets/components/sheet/primitives';
import { apiFetch } from '@/evennia_replacements/api';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';

interface Choice {
  value: string;
  label: string;
}

interface ProfileDrive {
  property_id: number;
  name: string;
  strength: number;
  strength_label: string;
}

export interface StandoffProfile {
  opted_in: boolean;
  cause: string;
  cause_label: string;
  drives: ProfileDrive[];
  locked: boolean;
  locked_reason: string;
  causes: Choice[];
  properties: Choice[];
  strengths: Choice[];
}

type ProfileChange =
  | { change: 'opt_in' | 'opt_out' }
  | { change: 'cause'; cause: string }
  | { change: 'drive'; property_id: number; strength: number }
  | { change: 'drop_drive'; property_id: number };

async function fetchProfile(sheetId: number): Promise<StandoffProfile> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/standoff-profile/`);
  if (!res.ok) throw new Error('Failed to load standoff profile');
  return (await res.json()) as StandoffProfile;
}

async function changeProfile(sheetId: number, change: ProfileChange): Promise<StandoffProfile> {
  const res = await apiFetch(`/api/character-sheets/${sheetId}/standoff-profile/`, {
    method: 'POST',
    body: JSON.stringify(change),
  });
  if (!res.ok) {
    const data = (await res.json().catch(() => null)) as { detail?: string } | null;
    throw new Error(data?.detail ?? 'Failed to change standoff profile');
  }
  return (await res.json()) as StandoffProfile;
}

interface StandoffProfilePanelProps {
  sheetId: number;
}

export function StandoffProfilePanel({ sheetId }: StandoffProfilePanelProps) {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [newProperty, setNewProperty] = useState('');
  const [newStrength, setNewStrength] = useState('1');
  const { data } = useQuery({
    queryKey: ['standoff-profile', sheetId],
    queryFn: () => fetchProfile(sheetId),
  });

  const change = useMutation({
    mutationFn: (next: ProfileChange) => changeProfile(sheetId, next),
    onSuccess: (profile) => {
      setError(null);
      queryClient.setQueryData(['standoff-profile', sheetId], profile);
    },
    onError: (err: Error) => setError(err.message),
  });

  if (!data) return null;

  const busy = change.isPending || data.locked;
  const heldIds = new Set(data.drives.map((drive) => String(drive.property_id)));
  const available = data.properties.filter((choice) => !heldIds.has(choice.value));

  return (
    <div className="refsheet-stack" data-testid="standoff-profile-panel">
      <Subheading>Standoffs</Subheading>
      {data.locked && <p className="refsheet-note">{data.locked_reason}</p>}
      {error && (
        <p className="refsheet-note" style={{ color: 'hsl(var(--destructive))' }}>
          {error}
        </p>
      )}

      <label className="flex items-center gap-3 text-sm">
        <Switch
          checked={data.opted_in}
          disabled={busy}
          aria-label="Open to being read and pressed"
          onCheckedChange={(checked) => change.mutate({ change: checked ? 'opt_in' : 'opt_out' })}
        />
        Open to being read and pressed
      </label>

      <div className="flex flex-col gap-1 text-sm">
        <span id="standoff-cause-label">Cause</span>
        <Select
          value={data.cause}
          disabled={busy}
          onValueChange={(cause) => change.mutate({ change: 'cause', cause })}
        >
          <SelectTrigger className="h-8 w-56" aria-labelledby="standoff-cause-label">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {data.causes.map((choice) => (
              <SelectItem key={choice.value} value={choice.value}>
                {choice.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col gap-2 text-sm">
        <span>Drives</span>
        {data.drives.length === 0 && <p className="refsheet-ledger">You have no drives.</p>}
        {data.drives.map((drive) => (
          <div key={drive.property_id} className="flex items-center gap-2">
            <span className="w-40">{drive.name}</span>
            <Select
              value={String(drive.strength)}
              disabled={busy}
              onValueChange={(strength) =>
                change.mutate({
                  change: 'drive',
                  property_id: drive.property_id,
                  strength: Number(strength),
                })
              }
            >
              <SelectTrigger className="h-8 w-32" aria-label={`Strength of ${drive.name}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.strengths.map((choice) => (
                  <SelectItem key={choice.value} value={choice.value}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={busy}
              onClick={() =>
                change.mutate({ change: 'drop_drive', property_id: drive.property_id })
              }
            >
              Drop
            </Button>
          </div>
        ))}
        {available.length > 0 && (
          <div className="flex items-center gap-2">
            <Select value={newProperty} disabled={busy} onValueChange={setNewProperty}>
              <SelectTrigger className="h-8 w-40" aria-label="Drive to add">
                <SelectValue placeholder="Add a drive" />
              </SelectTrigger>
              <SelectContent>
                {available.map((choice) => (
                  <SelectItem key={choice.value} value={choice.value}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={newStrength} disabled={busy} onValueChange={setNewStrength}>
              <SelectTrigger className="h-8 w-32" aria-label="Strength of the new drive">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {data.strengths.map((choice) => (
                  <SelectItem key={choice.value} value={choice.value}>
                    {choice.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              type="button"
              size="sm"
              disabled={busy || newProperty === ''}
              onClick={() => {
                change.mutate({
                  change: 'drive',
                  property_id: Number(newProperty),
                  strength: Number(newStrength),
                });
                setNewProperty('');
              }}
            >
              Add
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
