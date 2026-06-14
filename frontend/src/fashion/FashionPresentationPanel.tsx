/**
 * FashionPresentationPanel — present a look at an event and judge peers (#514).
 *
 * Lists the event's fashion presentations (presenter + current acclaim), lets
 * the viewer present their own look (optionally tagging a saved outfit), and
 * offers a per-row Judge action for every presentation that is not the
 * viewer's own. API 400 ``detail`` messages (e.g. "You cannot judge your own
 * presentation.") are surfaced inline.
 *
 * The presentation read shape carries ``presenter`` as a CharacterSheet pk
 * only — no name — so rows render the viewer's own name (resolved from the
 * active roster entry) and a neutral "Presenter #<pk>" label for others. A
 * follow-up to add ``presenter_name`` to the serializer would let every row
 * show a real name; see the PR notes.
 */
import { useMemo, useState } from 'react';
import { useAppSelector } from '@/store/hooks';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useOutfits } from '@/inventory/hooks/useOutfits';
import {
  useEventPresentationsQuery,
  useJudgePresentationMutation,
  usePresentOutfitMutation,
} from './queries';

interface FashionPresentationPanelProps {
  eventId: number;
}

export function FashionPresentationPanel({ eventId }: FashionPresentationPanelProps) {
  const activeCharacter = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const activeEntry = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacter) ?? null,
    [myRosterEntries, activeCharacter]
  );
  // CharacterSheet pk == roster character_id (CharacterSheet uses primary_key=True).
  const mySheetId = activeEntry?.character_id ?? null;

  const { data: presentations, isLoading, isError } = useEventPresentationsQuery(eventId);

  const { data: myOutfits = [] } = useOutfits(mySheetId ?? undefined);

  const presentMutation = usePresentOutfitMutation(eventId);
  const judgeMutation = useJudgePresentationMutation(eventId);

  const [selectedOutfit, setSelectedOutfit] = useState<string>('');

  const hasPresented = useMemo(
    () => (presentations ?? []).some((p) => p.presenter === mySheetId),
    [presentations, mySheetId]
  );

  const actionError = presentMutation.error?.message ?? judgeMutation.error?.message ?? null;

  const handlePresent = () => {
    const outfit = selectedOutfit ? Number(selectedOutfit) : undefined;
    presentMutation.mutate({ event: eventId, ...(outfit ? { outfit } : {}) });
  };

  return (
    <Card data-testid="fashion-panel">
      <CardHeader>
        <CardTitle className="text-base">Fashion Presentations</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Present-your-look controls */}
        <div className="flex flex-wrap items-center gap-2">
          {myOutfits.length > 0 && (
            <select
              aria-label="Outfit to present"
              className="h-9 rounded-md border border-input bg-background px-3 text-sm"
              value={selectedOutfit}
              onChange={(e) => setSelectedOutfit(e.target.value)}
              disabled={presentMutation.isPending}
            >
              <option value="">Current look (no saved outfit)</option>
              {myOutfits.map((outfit) => (
                <option key={outfit.id} value={String(outfit.id)}>
                  {outfit.name}
                </option>
              ))}
            </select>
          )}
          <Button
            onClick={handlePresent}
            disabled={presentMutation.isPending || mySheetId === null || hasPresented}
          >
            {hasPresented ? 'Already presented' : 'Present my look'}
          </Button>
        </div>

        {actionError && (
          <p className="text-sm text-destructive" role="alert" data-testid="fashion-error">
            {actionError}
          </p>
        )}

        {/* Presentation list */}
        {isLoading ? (
          <p className="text-sm text-muted-foreground">Loading presentations…</p>
        ) : isError ? (
          <p className="text-sm text-destructive" role="alert">
            Failed to load fashion presentations.
          </p>
        ) : (presentations ?? []).length === 0 ? (
          <p className="text-sm text-muted-foreground">No one has presented a look yet.</p>
        ) : (
          <ul className="space-y-2" data-testid="fashion-rows">
            {(presentations ?? []).map((p) => {
              const isOwn = p.presenter === mySheetId;
              const name = isOwn ? (activeEntry?.name ?? 'You') : `Presenter #${p.presenter}`;
              return (
                <li
                  key={p.id}
                  className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                >
                  <span className="flex items-baseline gap-2">
                    <span className="font-medium">{name}</span>
                    {isOwn && <span className="text-xs text-muted-foreground">(You)</span>}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="text-sm text-muted-foreground">Acclaim: {p.acclaim}</span>
                    {!isOwn && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => judgeMutation.mutate({ presentation: p.id })}
                        disabled={judgeMutation.isPending}
                      >
                        Judge
                      </Button>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
