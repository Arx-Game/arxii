/**
 * AlterationResolveDialog — resolve one PendingAlteration (#877).
 *
 * Two paths, two tabs: pick a tier/affinity-matched library template, or
 * author from scratch within the pending's tier caps. Both POST to
 * /api/magic/pending-alterations/{id}/resolve/.
 *
 * Shell pattern mirrors rituals/components/RitualPerformDialog.tsx.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { AlterationResolveError } from '../../api';
import { useAlterationLibrary, useResolveAlteration } from '../../queries';
import { getTierCaps } from '../../types';
import type { AlterationLibraryEntry, PendingAlteration } from '../../types';
import { AlterationAuthorForm } from './AlterationAuthorForm';

export interface AlterationResolveDialogProps {
  pending: PendingAlteration;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const RESOLVED_TOAST = 'The mark settles into your flesh. It is part of you now.';

/** Field keys that have dedicated per-field rendering in the form. */
const FORM_FIELD_KEYS = new Set(['name', 'player_description', 'observer_description']);

/**
 * Returns messages for fieldErrors keys that are NOT rendered per-field
 * and NOT the generic non_field_errors key (those already appear in error.message).
 */
function orphanedErrorLines(fieldErrors: Record<string, string[]>): string[] {
  const lines: string[] = [];
  for (const [key, msgs] of Object.entries(fieldErrors)) {
    if (key === 'non_field_errors' || FORM_FIELD_KEYS.has(key)) continue;
    lines.push(...msgs);
  }
  return lines;
}

export function AlterationResolveDialog({
  pending,
  open,
  onOpenChange,
}: AlterationResolveDialogProps) {
  const [selectedEntryId, setSelectedEntryId] = useState<number | null>(null);
  const { data: library, isLoading: libraryLoading } = useAlterationLibrary(
    open ? pending.id : null
  );
  const resolveMutation = useResolveAlteration();
  const caps = getTierCaps(pending);

  function handleOpenChange(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setSelectedEntryId(null);
      resolveMutation.reset();
    }
  }

  function onResolved() {
    toast.success(RESOLVED_TOAST);
    handleOpenChange(false);
  }

  function submitLibraryPick() {
    if (selectedEntryId == null) return;
    resolveMutation.mutate(
      { pendingId: pending.id, payload: { library_template_id: selectedEntryId } },
      { onSuccess: onResolved }
    );
  }

  const error = resolveMutation.error;
  const fieldErrors = error instanceof AlterationResolveError ? error.fieldErrors : {};
  const orphaned = orphanedErrorLines(fieldErrors);
  const bannerMessage = resolveMutation.isError && error instanceof Error ? error.message : null;
  const showBanner = bannerMessage !== null || orphaned.length > 0;

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Resolve your {pending.tier_display} Mage Scar</DialogTitle>
          <DialogDescription>
            {pending.character_name} was marked by {pending.origin_affinity_name} magic (
            {pending.origin_resonance_name}). This choice is permanent: take a known alteration from
            the library, or describe your own.
          </DialogDescription>
        </DialogHeader>

        {showBanner && (
          <div
            role="alert"
            className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {bannerMessage && <p>{bannerMessage}</p>}
            {orphaned.map((line) => (
              <p key={line}>{line}</p>
            ))}
          </div>
        )}

        <Tabs defaultValue="library">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="library">Choose from the Library</TabsTrigger>
            <TabsTrigger value="author">Author your own</TabsTrigger>
          </TabsList>

          {/* forceMount keeps both panels in the DOM so prose typed in "Author your own"
              survives a tab switch. The inactive panel is visually hidden via CSS. */}
          <TabsContent
            value="library"
            forceMount
            className="space-y-3 data-[state=inactive]:hidden"
          >
            {libraryLoading && <p className="text-sm text-muted-foreground">Searching…</p>}
            {!libraryLoading && (library ?? []).length === 0 && (
              <p className="text-sm text-muted-foreground">
                No library entries match this scar&apos;s tier and origin — author your own in the
                other tab.
              </p>
            )}
            {(library ?? []).map((entry) => (
              <LibraryEntryCard
                key={entry.id}
                entry={entry}
                selected={entry.id === selectedEntryId}
                onSelect={() => setSelectedEntryId(entry.id)}
              />
            ))}
            <div className="flex justify-end">
              <Button
                onClick={submitLibraryPick}
                disabled={selectedEntryId == null || resolveMutation.isPending}
              >
                {resolveMutation.isPending ? 'Resolving…' : 'Accept this mark'}
              </Button>
            </div>
          </TabsContent>

          <TabsContent value="author" forceMount className="data-[state=inactive]:hidden">
            <AlterationAuthorForm
              caps={caps}
              fieldErrors={fieldErrors}
              isPending={resolveMutation.isPending}
              onSubmit={(payload) =>
                resolveMutation.mutate(
                  { pendingId: pending.id, payload },
                  { onSuccess: onResolved }
                )
              }
            />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  );
}

function LibraryEntryCard({
  entry,
  selected,
  onSelect,
}: {
  entry: AlterationLibraryEntry;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={`w-full rounded-md border p-3 text-left transition-colors ${
        selected ? 'border-primary bg-primary/5' : 'hover:bg-muted/50'
      }`}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">{entry.name}</span>
        <span className="flex gap-1">
          {entry.weakness_magnitude > 0 && (
            <Badge variant="destructive">Weakness {entry.weakness_magnitude}</Badge>
          )}
          {entry.resonance_bonus_magnitude > 0 && (
            <Badge variant="secondary">Resonance +{entry.resonance_bonus_magnitude}</Badge>
          )}
          {entry.social_reactivity_magnitude > 0 && (
            <Badge variant="outline">Social {entry.social_reactivity_magnitude}</Badge>
          )}
          {entry.is_visible_at_rest && <Badge variant="outline">Always visible</Badge>}
        </span>
      </div>
      <p className="mt-1 text-sm italic text-muted-foreground">{entry.player_description}</p>
      <p className="mt-1 text-xs text-muted-foreground">Others see: {entry.observer_description}</p>
    </button>
  );
}
