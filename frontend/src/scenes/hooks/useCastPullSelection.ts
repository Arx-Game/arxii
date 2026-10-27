/**
 * useCastPullSelection — manages thread-pull selection state for the cast flow.
 *
 * Extracted from ActionPanel.tsx (#895 item 1, 2, 4) so the cluster can be
 * unit-tested in isolation. ActionPanel will adopt this hook in Task 4.
 *
 * Design notes:
 * - Threads are fetched only while ``castOpen`` is true (gated ``useThreads``).
 * - ``buildPullPayload`` returns ``{ error }`` instead of calling ``setPullNotice``
 *   inline so the component owns the side-effect (brief/item 4).
 * - ``reset()`` wipes ``selectedPulls`` and ``pullNotice``; call it after a
 *   successful cast or when the dialog closes.
 */

import { useEffect, useState, useMemo } from 'react';
import { useThreads, useCharacterResonances, usePullBurnPreview } from '@/magic/queries';
import type {
  Thread,
  ApplicablePullsRequest,
  BurnPreview,
  PullPreviewRequest,
} from '@/magic/types';
import type { CastableTechnique, CastPullRequestBody } from '@/scenes/actionTypes';
import { effectiveBurn } from '@/magic/burn';

// ---------------------------------------------------------------------------
// Public interface
// ---------------------------------------------------------------------------

export interface CastPullSelection {
  selectedPulls: Record<number, 0 | 1 | 2 | 3>;
  showInapplicable: boolean;
  setShowInapplicable: (next: boolean) => void;
  pullNotice: string | null;
  setPullNotice: (msg: string | null) => void;
  pullsContext: ApplicablePullsRequest | null;
  /** Resonance to burn for strain on this cast (#4736). */
  burn: number;
  setBurn: (next: number) => void;
  /** Burn numbers from the pull preview; null until a pull is chosen. */
  burnPreview: BurnPreview | null;
  /** The chosen pull's tier, for the ceiling line; null with no paid pull. */
  pullTier: 1 | 2 | 3 | null;
  balanceByResonanceId: Record<number, number>;
  handlePullsChange: (next: Record<number, 0 | 1 | 2 | 3>) => void;
  /** Returns ``{ pull }`` (or ``{}``) on success, or ``{ error }`` when the
   *  threads cache hasn't resolved for the changed thread yet. */
  buildPullPayload: () => { pull?: CastPullRequestBody } | { error: string };
  reset: () => void;
}

export interface UseCastPullSelectionParams {
  selectedTechnique: CastableTechnique | null;
  characterId: number | null;
  castTargetPersonaId: number | null;
  sceneId: string;
  castOpen: boolean;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useCastPullSelection(params: UseCastPullSelectionParams): CastPullSelection {
  const { selectedTechnique, characterId, castTargetPersonaId, sceneId, castOpen } = params;

  // Pull selection state — thread id → committed tier (0 = unpaid).
  const [selectedPulls, setSelectedPulls] = useState<Record<number, 0 | 1 | 2 | 3>>({});
  const [showInapplicable, setShowInapplicable] = useState(false);
  const [pullNotice, setPullNotice] = useState<string | null>(null);
  const [burn, setBurn] = useState(0);

  // A burn is sized against the technique's ceiling; a new technique starts over.
  const selectedTechniqueId = selectedTechnique?.id ?? null;
  useEffect(() => {
    setBurn(0);
  }, [selectedTechniqueId]);

  // Threads — fetched only while the cast dialog is open to avoid an
  // unnecessary warm-up fetch and to allow the gating test (brief item 6).
  const { data: threadsData } = useThreads({ enabled: castOpen });
  const threadById = useMemo(() => {
    const map = new Map<number, Thread>();
    for (const thread of threadsData?.results ?? []) {
      map.set(thread.id, thread);
    }
    return map;
  }, [threadsData]);

  // Resonance balances — used by ThreadPullPicker for unaffordable-tier tooltips.
  const { data: resonances } = useCharacterResonances(characterId ?? undefined);
  const balanceByResonanceId = useMemo<Record<number, number>>(() => {
    if (!resonances) return {};
    return Object.fromEntries(resonances.map((cr) => [cr.resonance, cr.balance ?? 0]));
  }, [resonances]);

  // Applicability context for the thread-pull picker — only while a technique
  // is selected in the open cast section.
  const pullsContext = useMemo<ApplicablePullsRequest | null>(() => {
    if (!castOpen || !selectedTechnique || characterId === null) return null;
    return {
      character_sheet_id: characterId,
      technique_id: selectedTechnique.id,
      target_persona_id: castTargetPersonaId,
      scene_id: Number(sceneId),
    };
  }, [castOpen, selectedTechnique, characterId, castTargetPersonaId, sceneId]);

  // Burn ceiling: preview the chosen pull against the selected technique.
  const pullGroup = useMemo(() => {
    const paid = Object.entries(selectedPulls).filter(([, tier]) => tier > 0);
    if (paid.length === 0) return null;
    const thread = threadById.get(Number(paid[0][0]));
    if (!thread) return null;
    return {
      resonanceId: thread.resonance,
      tier: paid[0][1] as 1 | 2 | 3,
      threadIds: paid.map(([id]) => Number(id)),
    };
  }, [selectedPulls, threadById]);
  const pullTier = pullGroup?.tier ?? null;
  const previewRequest = useMemo<PullPreviewRequest | null>(() => {
    if (!castOpen || !selectedTechnique || characterId === null || !pullGroup) return null;
    return {
      character_sheet_id: characterId,
      resonance_id: pullGroup.resonanceId,
      tier: pullGroup.tier,
      thread_ids: pullGroup.threadIds,
      technique_id: selectedTechnique.id,
    };
  }, [castOpen, selectedTechnique, characterId, pullGroup]);
  const { data: burnPreviewData } = usePullBurnPreview(previewRequest);
  const burnPreview = previewRequest ? (burnPreviewData?.burn ?? null) : null;

  /**
   * Constrain pull selection to a single (resonance, tier) group — the cast
   * payload's pull declaration is singular, so any newly raised pull reverts
   * every other paid pull that disagrees on resonance or tier.
   *
   * Lifted verbatim from ActionPanel.tsx:282-315.
   */
  function handlePullsChange(next: Record<number, 0 | 1 | 2 | 3>): void {
    const changed = Object.entries(next).find(
      ([id, tier]) => (selectedPulls[Number(id)] ?? 0) !== tier && tier > 0
    );
    if (changed) {
      const changedId = Number(changed[0]);
      const changedTier = changed[1];
      const changedResonance = threadById.get(changedId)?.resonance;
      if (changedResonance === undefined) {
        // Threads cache not resolved yet — can't group by resonance; pass
        // through unconstrained rather than reverting on undefined matches.
        setSelectedPulls(next);
        return;
      }
      let reverted = 0;
      const constrained = { ...next };
      for (const [idStr, tier] of Object.entries(next)) {
        const id = Number(idStr);
        if (id === changedId || tier === 0) continue;
        if (tier !== changedTier || threadById.get(id)?.resonance !== changedResonance) {
          constrained[id] = 0;
          reverted++;
        }
      }
      setPullNotice(reverted > 0 ? 'Pulls in one cast share a single resonance and tier.' : null);
      setSelectedPulls(constrained);
      return;
    }
    // Deselects pass through; a conflict notice is stale once no paid pull remains.
    if (!Object.values(next).some((tier) => tier > 0)) {
      setPullNotice(null);
    }
    setSelectedPulls(next);
  }

  /**
   * Build the pull payload for ``castTechnique``.
   *
   * Returns:
   * - ``{ pull: CastPullRequestBody }`` — paid group found and threads resolved.
   * - ``{}`` — no paid pulls selected (valid; cast proceeds without a pull).
   * - ``{ error: string }`` — paid pulls exist but the thread isn't in the cache
   *   yet; the component should surface this and abort the cast.
   *
   * Adapted from ActionPanel.tsx:317-334 — returns ``{ error }`` instead of
   * calling ``setPullNotice`` inline so the component owns that side-effect.
   */
  function buildPullPayload(): { pull?: CastPullRequestBody } | { error: string } {
    const paid = Object.entries(selectedPulls).filter(([, tier]) => tier > 0);
    if (paid.length === 0) return {};
    const firstThread = threadById.get(Number(paid[0][0]));
    if (!firstThread) {
      return { error: 'Thread data is still loading; try again in a moment.' };
    }
    const pull: CastPullRequestBody = {
      resonance_id: firstThread.resonance,
      tier: paid[0][1] as 1 | 2 | 3,
      thread_ids: paid.map(([id]) => Number(id)),
    };
    // The ceiling can shrink when the pull changes; never send past it.
    const burnToSend = effectiveBurn(burnPreview, burn);
    if (burnToSend > 0) pull.burn = burnToSend;
    return { pull };
  }

  function reset(): void {
    setSelectedPulls({});
    setPullNotice(null);
    setBurn(0);
  }

  return {
    selectedPulls,
    showInapplicable,
    setShowInapplicable,
    pullNotice,
    setPullNotice,
    pullsContext,
    burn,
    setBurn,
    burnPreview,
    pullTier,
    balanceByResonanceId,
    handlePullsChange,
    buildPullPayload,
    reset,
  };
}
