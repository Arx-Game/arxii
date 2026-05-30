/**
 * DeepLinkModalHost — the single Redux-driven host that renders the deep-link
 * modal for all 5 DeepLinkKind values (#551).
 *
 * Mounted once per CombatScenePage. Reads `state.deepLinkModal.current` and,
 * when set, renders a Radix Dialog whose content is chosen by `current.modal`:
 *
 *   - condition   → <ConditionDetailModal /> (own React Query fetch)
 *   - clash       → reuse ActiveState's <ClashCard /> from the seeded encounter
 *   - opponent    → name / tier / health from the encounter cache
 *   - participant → name / status / health from the encounter cache
 *   - combo       → minimal labelled fallback ("Combo #<id>")
 *
 * The 4 cache-reuse kinds read from useCombatEncounter(encounterId) — they do
 * NOT refetch per-entity. When the entity isn't found in cache, a minimal
 * "Details unavailable" fallback renders. Content stays thin and reuse-first.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { closeDeepLink } from '@/store/deepLinkModalSlice';
import { useCombatEncounter } from '@/combat/queries';
import { ClashCard } from '@/combat/sections/ActiveState';
import type { ClashState } from '@/combat/types';
import { ConditionDetailModal } from './ConditionDetailModal';

export interface DeepLinkModalHostProps {
  encounterId: number;
}

// ---------------------------------------------------------------------------
// Minimal fallback content
// ---------------------------------------------------------------------------

function UnavailableContent({ label }: { label: string }) {
  return (
    <DialogHeader>
      <DialogTitle>{label}</DialogTitle>
      <DialogDescription data-testid="deep-link-unavailable">
        Details unavailable.
      </DialogDescription>
    </DialogHeader>
  );
}

export function DeepLinkModalHost({ encounterId }: DeepLinkModalHostProps) {
  const dispatch = useAppDispatch();
  const current = useAppSelector((state) => state.deepLinkModal.current);

  // Encounter cache backs the clash / opponent / participant kinds. The hook is
  // a no-op fetch when encounterId <= 0; it returns the cached payload seeded by
  // the page's primary encounter query.
  const { data: encounter } = useCombatEncounter(encounterId);

  if (!current) return null;

  return (
    <Dialog
      open
      onOpenChange={(open) => {
        if (!open) dispatch(closeDeepLink());
      }}
    >
      <DialogContent className="max-w-md" data-testid="deep-link-modal-content">
        {renderContent(current.modal, current.id, encounter)}
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Content switch
// ---------------------------------------------------------------------------

function renderContent(
  modal: string,
  id: number,
  encounter: ReturnType<typeof useCombatEncounter>['data']
) {
  switch (modal) {
    case 'condition':
      return <ConditionDetailModal id={id} />;

    case 'clash': {
      // EncounterDetail.clashes is typed opaquely in the generated schema —
      // cast to the concrete ClashState[] (same as ActiveState does).
      const clashes = (encounter?.clashes ?? []) as unknown as ClashState[];
      const clash = clashes.find((c) => c.id === id);
      if (!clash) return <UnavailableContent label={`Clash #${id}`} />;
      const opponentName = encounter?.opponents.find((o) => o.id === clash.npc_opponent)?.name;
      return (
        <>
          <DialogHeader>
            <DialogTitle>Clash</DialogTitle>
            <DialogDescription className="sr-only">Active clash detail</DialogDescription>
          </DialogHeader>
          <ClashCard clash={clash} opponentName={opponentName} />
        </>
      );
    }

    case 'opponent': {
      const opponent = encounter?.opponents.find((o) => o.id === id);
      if (!opponent) return <UnavailableContent label={`Opponent #${id}`} />;
      return (
        <>
          <DialogHeader>
            <DialogTitle>{opponent.name}</DialogTitle>
            <DialogDescription>Tier: {opponent.tier}</DialogDescription>
          </DialogHeader>
          <div className="text-sm text-muted-foreground" data-testid="opponent-modal-body">
            Health: {opponent.health} / {opponent.max_health}
          </div>
        </>
      );
    }

    case 'participant': {
      const participant = encounter?.participants.find((p) => p.id === id);
      if (!participant) return <UnavailableContent label={`Participant #${id}`} />;
      return (
        <>
          <DialogHeader>
            <DialogTitle>{participant.character_name}</DialogTitle>
            {participant.character_status && (
              <DialogDescription>{participant.character_status}</DialogDescription>
            )}
          </DialogHeader>
          <div className="text-sm text-muted-foreground" data-testid="participant-modal-body">
            {participant.health !== null && participant.max_health !== null
              ? `Health: ${participant.health} / ${participant.max_health}`
              : 'Health hidden.'}
          </div>
        </>
      );
    }

    case 'combo':
    default:
      // Combo has no dedicated detail endpoint — render a thin labelled
      // fallback rather than over-engineering a new fetch path.
      return (
        <>
          <DialogHeader>
            <DialogTitle>{`Combo #${id}`}</DialogTitle>
            <DialogDescription>Combo details are unavailable here.</DialogDescription>
          </DialogHeader>
        </>
      );
  }
}
