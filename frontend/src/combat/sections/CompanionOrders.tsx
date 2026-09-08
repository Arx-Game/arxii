/** Web controls for directing deployed companions in a combat encounter (#3576). */

import { useMemo, useState } from 'react';
import { PawPrint } from 'lucide-react';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useMyCompanions } from '@/companions/queries';
import type { CompanionSummary } from '@/companions/types';
import { isDispatchFailure, type EncounterDetail, type Opponent, type Participant } from '../types';
import { useRegistryDispatch } from '../queries';

type CompanionOrderKind = 'attack_target' | 'hold' | 'defend_ally';

type CompanionOrderSummary = NonNullable<EncounterDetail['companion_orders']>[number];

type DraftOrder = {
  kind: CompanionOrderKind | null;
  targetId: number | null;
  allyId: number | null;
};

interface CompanionOrdersProps {
  encounter: EncounterDetail;
  encounterId: number;
  characterId: number;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

const ORDER_LABELS: Record<CompanionOrderKind, string> = {
  attack_target: 'Attack',
  hold: 'Hold',
  defend_ally: 'Defend',
};

function draftFor(order: CompanionOrderSummary | undefined): DraftOrder {
  return {
    kind: (order?.order_kind as CompanionOrderKind | undefined) ?? null,
    targetId: order?.target_opponent_id ?? null,
    allyId: order?.defending_participant_id ?? null,
  };
}

function sameDraft(a: DraftOrder, b: DraftOrder): boolean {
  return a.kind === b.kind && a.targetId === b.targetId && a.allyId === b.allyId;
}

function orderSummary(
  order: CompanionOrderSummary | undefined,
  participants: Participant[],
  opponents: Opponent[]
): string {
  if (order === undefined) return 'No order this round';
  if (order.order_kind === 'attack_target') {
    return `Attack ${opponents.find((opponent) => opponent.id === order.target_opponent_id)?.name ?? 'target'}`;
  }
  if (order.order_kind === 'defend_ally') {
    return `Defend ${participants.find((participant) => participant.id === order.defending_participant_id)?.character_name ?? 'ally'}`;
  }
  return 'Hold';
}

function activeCompanionOpponent(
  companion: CompanionSummary,
  opponents: Opponent[]
): Opponent | undefined {
  return opponents.find(
    (opponent) =>
      opponent.status === 'active' &&
      companion.objectdb_id !== null &&
      opponent.objectdb_id === companion.objectdb_id
  );
}

interface CompanionOrderCardProps {
  companion: CompanionSummary;
  encounter: EncounterDetail;
  encounterId: number;
  characterId: number;
  deployedOpponent: Opponent;
}

function CompanionOrderCard({
  companion,
  encounter,
  encounterId,
  characterId,
  deployedOpponent,
}: CompanionOrderCardProps) {
  const { mutateAsync, isPending } = useRegistryDispatch(encounterId, characterId);
  const [draft, setDraft] = useState<DraftOrder>(() =>
    draftFor(encounter.companion_orders?.find((order) => order.companion_id === companion.id))
  );
  const [error, setError] = useState<string | null>(null);

  const savedOrder = encounter.companion_orders?.find(
    (order) => order.companion_id === companion.id
  );
  const savedDraft = draftFor(savedOrder);
  const isDirty = !sameDraft(draft, savedDraft);
  const activeEnemies = useMemo(
    () =>
      encounter.opponents.filter(
        (opponent) =>
          opponent.status === 'active' &&
          opponent.allegiance === 'enemy' &&
          opponent.id !== deployedOpponent.id
      ),
    [encounter.opponents, deployedOpponent.id]
  );
  const activeAllies = encounter.participants.filter(
    (participant) => participant.status === 'active'
  );

  function selectKind(kind: CompanionOrderKind): void {
    setError(null);
    const next: DraftOrder = { kind, targetId: null, allyId: null };
    setDraft(next);
    if (kind === 'hold') {
      dispatch(next).catch(() => {});
    }
  }

  async function dispatch(order: DraftOrder): Promise<void> {
    if (order.kind === null) return;
    if (order.kind === 'attack_target' && order.targetId === null) {
      setError('Select an enemy to attack.');
      return;
    }
    if (order.kind === 'defend_ally' && order.allyId === null) {
      setError('Select an ally to defend.');
      return;
    }
    setError(null);
    try {
      const result = await mutateAsync({
        registryKey: 'order_companion',
        kwargs: {
          companion_id: companion.id,
          order_kind: order.kind,
          ...(order.targetId !== null ? { target_id: order.targetId } : {}),
          ...(order.allyId !== null ? { ally_id: order.allyId } : {}),
        },
      });
      if (isDispatchFailure(result)) {
        setDraft(savedDraft);
        setError(result.message ?? 'That companion order was rejected.');
        return;
      }
      toast.success(result.message ?? `${companion.name} has a new order.`);
    } catch {
      setDraft(savedDraft);
      setError('The companion order could not be sent.');
    }
  }

  return (
    <div
      className="space-y-2 border-t border-border px-3 py-2"
      data-testid={`companion-order-${companion.id}`}
    >
      <div className="flex items-center gap-2">
        <PawPrint className="h-4 w-4 shrink-0 text-amber-500" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-xs font-semibold text-foreground">{companion.name}</p>
          <p className="truncate text-[10px] text-muted-foreground">
            {companion.archetype.name} ·{' '}
            {orderSummary(savedOrder, encounter.participants, encounter.opponents)}
          </p>
        </div>
      </div>
      <div className="grid grid-cols-3 gap-1" role="group" aria-label={`Order ${companion.name}`}>
        {(Object.keys(ORDER_LABELS) as CompanionOrderKind[]).map((kind) => {
          const selected = draft.kind === kind;
          return (
            <button
              key={kind}
              type="button"
              aria-pressed={selected}
              data-testid={`companion-${kind}-${companion.id}`}
              onClick={() => selectKind(kind)}
              className={cn(
                'rounded border px-2 py-1.5 text-[11px] font-semibold transition-colors',
                selected
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border bg-muted/50 text-muted-foreground hover:border-primary/50 hover:text-foreground'
              )}
            >
              {ORDER_LABELS[kind]}
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-muted-foreground">
        Choose another order to switch. Inactive choices remain clickable.
      </p>
      {draft.kind === 'attack_target' && (
        <Select
          value={draft.targetId === null ? '' : String(draft.targetId)}
          onValueChange={(value) =>
            setDraft((previous) => ({ ...previous, targetId: Number(value) }))
          }
          disabled={isPending}
        >
          <SelectTrigger
            data-testid={`companion-attack-target-${companion.id}`}
            className="h-8 text-xs"
          >
            <SelectValue placeholder="Attack an enemy..." />
          </SelectTrigger>
          <SelectContent>
            {activeEnemies.map((opponent) => (
              <SelectItem key={opponent.id} value={String(opponent.id)}>
                {opponent.name}
              </SelectItem>
            ))}
            {activeEnemies.length === 0 && (
              <SelectItem value="__none__" disabled>
                No active enemies
              </SelectItem>
            )}
          </SelectContent>
        </Select>
      )}
      {draft.kind === 'defend_ally' && (
        <Select
          value={draft.allyId === null ? '' : String(draft.allyId)}
          onValueChange={(value) =>
            setDraft((previous) => ({ ...previous, allyId: Number(value) }))
          }
          disabled={isPending}
        >
          <SelectTrigger
            data-testid={`companion-defend-ally-${companion.id}`}
            className="h-8 text-xs"
          >
            <SelectValue placeholder="Defend an ally..." />
          </SelectTrigger>
          <SelectContent>
            {activeAllies.map((participant) => (
              <SelectItem key={participant.id} value={String(participant.id)}>
                {participant.character_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {draft.kind !== null && draft.kind !== 'hold' && (
        <div className="flex gap-1">
          {isDirty && (
            <button
              type="button"
              data-testid={`companion-reset-${companion.id}`}
              onClick={() => {
                setDraft(savedDraft);
                setError(null);
              }}
              disabled={isPending}
              className="flex-1 rounded border border-border bg-muted px-2 py-1.5 text-[11px] text-muted-foreground hover:bg-muted/80 disabled:opacity-50"
            >
              Reset
            </button>
          )}
          <button
            type="button"
            data-testid={`companion-confirm-${companion.id}`}
            onClick={() => dispatch(draft).catch(() => {})}
            disabled={isPending}
            className="flex-1 rounded border border-primary bg-primary px-2 py-1.5 text-[11px] font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {isPending ? 'Ordering...' : 'Confirm order'}
          </button>
        </div>
      )}
      {error !== null && (
        <p role="alert" className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

export function CompanionOrders({
  encounter,
  encounterId,
  characterId,
  collapsed = false,
  onToggleCollapse,
}: CompanionOrdersProps) {
  const { data: companions = [] } = useMyCompanions();
  const deployed = companions.flatMap((companion) => {
    const opponent = activeCompanionOpponent(companion, encounter.opponents);
    return opponent === undefined ? [] : [{ companion, opponent }];
  });

  if (!encounter.is_participant || encounter.status !== 'declaring' || deployed.length === 0) {
    return null;
  }

  return (
    <div className="rounded-md border border-border bg-card" data-testid="companion-orders-section">
      <button
        type="button"
        onClick={onToggleCollapse}
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        aria-expanded={!collapsed}
        data-testid="companion-orders-toggle"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Companions
        </span>
        <span
          className={cn(
            'text-muted-foreground transition-transform',
            collapsed ? '-rotate-90' : 'rotate-0'
          )}
          aria-hidden="true"
        >
          ▾
        </span>
      </button>
      {!collapsed &&
        deployed.map(({ companion, opponent }) => (
          <CompanionOrderCard
            key={companion.id}
            companion={companion}
            encounter={encounter}
            encounterId={encounterId}
            characterId={characterId}
            deployedOpponent={opponent}
          />
        ))}
    </div>
  );
}
