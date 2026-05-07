/**
 * SineatingRequestDialog — Sinner-initiated Sineating request form.
 *
 * Allows a Sinner to send a Sineating offer to their bonded Sineater.
 * Fields: Sineater (character search), Resonance (select), Scene (select),
 * Units (int, capped at hollowMax - hollowCurrent).
 *
 * Shell pattern mirrors AcceptOfferDialog.tsx.
 * Character search follows InviteToTableDialog.tsx (debounced persona search).
 */

import { useState, useEffect, useRef } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
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
import { searchPersonas } from '@/events/queries';
import { fetchScenes } from '@/scenes/queries';
import type { SceneListItem } from '@/scenes/queries';
import { useRequestSineating, useCharacterResonances } from '../queries';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface PersonaOption {
  id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface SineatingRequestDialogProps {
  sinnerSheetId: number;
  hollowCurrent: number;
  hollowMax: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSuccess?: () => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function extractErrorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return 'Failed to send Sineating request';
}

async function fetchActiveScenes(): Promise<{ results: SceneListItem[] }> {
  return (await fetchScenes('status=active')) as { results: SceneListItem[] };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SineatingRequestDialog({
  sinnerSheetId,
  hollowCurrent,
  hollowMax,
  open,
  onOpenChange,
  onSuccess,
}: SineatingRequestDialogProps) {
  const availableUnits = Math.max(0, hollowMax - hollowCurrent);

  // Form state
  const [sineaterQuery, setSineaterQuery] = useState('');
  const [sineaterResults, setSineaterResults] = useState<PersonaOption[]>([]);
  const [selectedSineater, setSelectedSineater] = useState<PersonaOption | null>(null);
  const [sineaterSearching, setSineaterSearching] = useState(false);
  const [resonanceId, setResonanceId] = useState<number | null>(null);
  const [sceneId, setSceneId] = useState<number | null>(null);
  const [units, setUnits] = useState<number | ''>('');

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Data hooks
  const { data: resonances, isLoading: resonancesLoading } = useCharacterResonances();
  const { data: scenesData, isLoading: scenesLoading } = useQuery({
    queryKey: ['scenes', 'active'],
    queryFn: fetchActiveScenes,
    enabled: open,
  });
  const scenes = scenesData?.results ?? [];
  const resonanceList = resonances ?? [];

  // Mutation
  const requestMutation = useRequestSineating();

  // Debounced sineater search
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (sineaterQuery.trim().length < 2) {
      setSineaterResults([]);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setSineaterSearching(true);
      searchPersonas(sineaterQuery.trim())
        .then((results) => setSineaterResults(results))
        .catch(() => setSineaterResults([]))
        .finally(() => setSineaterSearching(false));
    }, 300);
  }, [sineaterQuery]);

  function resetForm() {
    setSineaterQuery('');
    setSineaterResults([]);
    setSelectedSineater(null);
    setResonanceId(null);
    setSceneId(null);
    setUnits('');
    requestMutation.reset();
  }

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) resetForm();
  }

  function handleSelectSineater(persona: PersonaOption) {
    setSelectedSineater(persona);
    setSineaterQuery(persona.name);
    setSineaterResults([]);
  }

  // Validation
  const unitsNum = typeof units === 'number' ? units : NaN;
  const unitsValid = Number.isFinite(unitsNum) && unitsNum >= 1 && unitsNum <= availableUnits;
  const canSubmit =
    selectedSineater !== null &&
    resonanceId !== null &&
    sceneId !== null &&
    unitsValid &&
    !requestMutation.isPending;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit || selectedSineater === null || resonanceId === null || sceneId === null) return;

    requestMutation.mutate(
      {
        actor_sheet_id: sinnerSheetId,
        sineater_sheet_id: selectedSineater.id,
        resonance_id: resonanceId,
        max_units: unitsNum,
        scene_id: sceneId,
      },
      {
        onSuccess: () => {
          handleOpenChange(false);
          onSuccess?.();
        },
        onError: () => {
          // Error is surfaced via requestMutation.isError in the banner
        },
      }
    );
  }

  const errorMessage = requestMutation.isError ? extractErrorMessage(requestMutation.error) : null;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Request Sineating</DialogTitle>
            <DialogDescription>
              Ask your bonded Sineater to eat sins from your Hollow. Up to{' '}
              <strong data-testid="available-units">{availableUnits}</strong> units available.
            </DialogDescription>
          </DialogHeader>

          {/* Error banner */}
          {errorMessage && (
            <div
              className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
              data-testid="sineating-error-banner"
            >
              <p>{errorMessage}</p>
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Sineater search */}
            <div className="space-y-1.5">
              <Label htmlFor="sineater-search">Sineater *</Label>
              <div className="relative">
                <Input
                  id="sineater-search"
                  data-testid="sineater-search-input"
                  value={sineaterQuery}
                  onChange={(e) => {
                    setSineaterQuery(e.target.value);
                    setSelectedSineater(null);
                  }}
                  placeholder="Search for your Sineater…"
                  autoComplete="off"
                  disabled={requestMutation.isPending}
                />
                {sineaterSearching && (
                  <span className="absolute right-2 top-2 text-xs text-muted-foreground">
                    Searching…
                  </span>
                )}
                {sineaterResults.length > 0 && (
                  <ul className="absolute z-50 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-popover shadow-lg">
                    {sineaterResults.map((p) => (
                      <li key={p.id}>
                        <button
                          type="button"
                          className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                          onClick={() => handleSelectSineater(p)}
                        >
                          {p.name}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>

            {/* Resonance picker */}
            <div className="space-y-1.5">
              <Label htmlFor="resonance-select">Resonance *</Label>
              <Select
                value={resonanceId != null ? String(resonanceId) : ''}
                onValueChange={(val) => setResonanceId(Number(val))}
                disabled={requestMutation.isPending || resonancesLoading}
              >
                <SelectTrigger id="resonance-select" data-testid="resonance-select-trigger">
                  <SelectValue
                    placeholder={resonancesLoading ? 'Loading resonances…' : 'Select a resonance'}
                  />
                </SelectTrigger>
                <SelectContent>
                  {resonanceList.map((cr) => (
                    <SelectItem key={cr.id} value={String(cr.id)}>
                      {cr.resonance_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Scene picker */}
            <div className="space-y-1.5">
              <Label htmlFor="scene-select">Scene *</Label>
              <Select
                value={sceneId != null ? String(sceneId) : ''}
                onValueChange={(val) => setSceneId(Number(val))}
                disabled={requestMutation.isPending || scenesLoading}
              >
                <SelectTrigger id="scene-select" data-testid="scene-select-trigger">
                  <SelectValue placeholder={scenesLoading ? 'Loading scenes…' : 'Select a scene'} />
                </SelectTrigger>
                <SelectContent>
                  {scenes.map((scene) => (
                    <SelectItem key={scene.id} value={String(scene.id)}>
                      {scene.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* Units input */}
            <div className="space-y-1.5">
              <Label htmlFor="sineating-units">
                Units <span className="text-xs text-muted-foreground">(1–{availableUnits})</span>
              </Label>
              <Input
                id="sineating-units"
                data-testid="sineating-units-input"
                type="number"
                min={1}
                max={availableUnits}
                value={units}
                onChange={(e) => {
                  const val = e.target.value;
                  setUnits(val === '' ? '' : Number(val));
                }}
                placeholder={`1–${availableUnits}`}
                disabled={requestMutation.isPending || availableUnits === 0}
              />
              {availableUnits === 0 && (
                <p className="text-xs text-muted-foreground">
                  Hollow is already at maximum capacity.
                </p>
              )}
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              data-testid="sineating-cancel-button"
              onClick={() => handleOpenChange(false)}
              disabled={requestMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" data-testid="sineating-request-submit" disabled={!canSubmit}>
              {requestMutation.isPending ? 'Sending…' : 'Send Request'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
