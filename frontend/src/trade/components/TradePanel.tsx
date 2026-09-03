/**
 * TradePanel — the two-sided negotiated trade staging UI (#2990).
 *
 * Two columns (your offer / their offer): staged items, a coin amount, and a
 * confirm state per side. An item picker sourced from `useInventory` (your
 * `carried_items`) lets you stage anything you're holding; staging or
 * changing the coin amount resets both confirms server-side, so the panel
 * just re-renders off the next poll/invalidation rather than tracking that
 * itself. `TradeSession.initiator_sheet`/`counterparty_sheet` are
 * `CharacterSheet` ids, which share ObjectDB's pk 1:1 (CLAUDE.md) — so they
 * compare directly against `actorCharacterId` with no extra lookup.
 */

import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { formatCoppers } from '@/lib/currency';
import { useInventory } from '@/inventory/hooks/useInventory';
import type { TradeItemStake } from '../api';
import {
  useAcceptTrade,
  useCancelTrade,
  useConfirmTrade,
  useSetTradeCoin,
  useStageTradeItem,
  useTradeSession,
  useUnstageTradeItem,
} from '../queries';

export interface TradePanelProps {
  sessionId: number;
  /** ObjectDB pk of the viewer's active character. */
  actorCharacterId: number;
}

function parseNonNegativeAmount(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) return null;
  return Number.parseInt(trimmed, 10);
}

interface SideProps {
  title: string;
  coppers: number;
  confirmed: boolean;
  stakes: TradeItemStake[];
  isMine: boolean;
  isActive: boolean;
  onUnstage?: (stakeId: number) => void;
  unstageBusy?: boolean;
}

function TradeSide({
  title,
  coppers,
  confirmed,
  stakes,
  isMine,
  isActive,
  onUnstage,
  unstageBusy,
}: SideProps) {
  return (
    <div className="flex-1 space-y-2 rounded-md border p-3" data-testid={`trade-side-${title}`}>
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-medium">{title}</h4>
        <span
          className={confirmed ? 'text-xs text-green-600' : 'text-xs text-muted-foreground'}
          data-testid={`trade-confirmed-${title}`}
        >
          {confirmed ? 'Confirmed' : 'Not confirmed'}
        </span>
      </div>
      <p className="text-sm text-muted-foreground">{formatCoppers(coppers)}</p>
      <ul className="space-y-1">
        {stakes.map((stake) => (
          <li key={stake.id} className="flex items-center justify-between text-sm">
            <span>{stake.item_name}</span>
            {isMine && isActive && onUnstage && (
              <Button
                size="sm"
                variant="ghost"
                disabled={unstageBusy}
                onClick={() => onUnstage(stake.id)}
                data-testid={`unstage-${stake.id}`}
              >
                Remove
              </Button>
            )}
          </li>
        ))}
        {stakes.length === 0 && <li className="text-sm text-muted-foreground">Nothing offered.</li>}
      </ul>
    </div>
  );
}

export function TradePanel({ sessionId, actorCharacterId }: TradePanelProps) {
  const { data: session } = useTradeSession(sessionId);
  const [coinText, setCoinText] = useState('');
  const [error, setError] = useState<string | null>(null);

  const accept = useAcceptTrade(actorCharacterId, sessionId);
  const stage = useStageTradeItem(actorCharacterId, sessionId);
  const unstage = useUnstageTradeItem(actorCharacterId, sessionId);
  const setCoin = useSetTradeCoin(actorCharacterId, sessionId);
  const confirm = useConfirmTrade(actorCharacterId, sessionId);
  const cancel = useCancelTrade(actorCharacterId, sessionId);

  const isActive = session?.status === 'active';
  const { data: inventory } = useInventory(isActive ? actorCharacterId : undefined);

  if (!session) return null;

  const viewerIsInitiator = session.initiator_sheet === actorCharacterId;
  const mySheetId = viewerIsInitiator ? session.initiator_sheet : session.counterparty_sheet;
  const myStakes = session.item_stakes.filter((s) => s.offered_by_sheet === mySheetId);
  const theirStakes = session.item_stakes.filter((s) => s.offered_by_sheet !== mySheetId);
  const myCoppers = viewerIsInitiator ? session.initiator_coppers : session.counterparty_coppers;
  const theirCoppers = viewerIsInitiator ? session.counterparty_coppers : session.initiator_coppers;
  const myConfirmed = viewerIsInitiator
    ? session.initiator_confirmed
    : session.counterparty_confirmed;
  const theirConfirmed = viewerIsInitiator
    ? session.counterparty_confirmed
    : session.initiator_confirmed;
  const stagedItemIds = new Set(session.item_stakes.map((s) => s.item_instance));
  const stageableItems = (inventory ?? []).filter(
    (item) => item.game_object_id !== null && !stagedItemIds.has(item.id)
  );

  function runMutation(fn: () => Promise<unknown>) {
    setError(null);
    fn().catch((err) => setError(err instanceof Error ? err.message : 'Trade action failed.'));
  }

  const renderConfirm = () => {
    if (confirm.isPending) {
      return 'Confirming…';
    }
    if (myConfirmed) {
      return 'Confirmed';
    }
    return 'Confirm';
  };

  return (
    <Card data-testid="trade-panel">
      <CardHeader className="pb-3">
        <CardTitle className="text-base">
          Trade with {viewerIsInitiator ? session.counterparty_name : session.initiator_name}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {session.status === 'proposed' && !viewerIsInitiator && (
          <Button
            size="sm"
            disabled={accept.isPending}
            onClick={() => runMutation(() => accept.mutateAsync())}
            data-testid="accept-trade-button"
          >
            {accept.isPending ? 'Accepting…' : 'Accept Trade'}
          </Button>
        )}
        {session.status === 'proposed' && viewerIsInitiator && (
          <p className="text-sm text-muted-foreground">Waiting for them to accept.</p>
        )}

        {(session.status === 'active' || session.status === 'completed') && (
          <div className="flex flex-col gap-3 sm:flex-row">
            <TradeSide
              title="Your Offer"
              coppers={myCoppers}
              confirmed={myConfirmed}
              stakes={myStakes}
              isMine
              isActive={isActive}
              onUnstage={(stakeId) => runMutation(() => unstage.mutateAsync(stakeId))}
              unstageBusy={unstage.isPending}
            />
            <TradeSide
              title="Their Offer"
              coppers={theirCoppers}
              confirmed={theirConfirmed}
              stakes={theirStakes}
              isMine={false}
              isActive={isActive}
            />
          </div>
        )}

        {isActive && (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <label htmlFor={`trade-coin-${sessionId}`} className="sr-only">
                Coin to offer
              </label>
              <Input
                id={`trade-coin-${sessionId}`}
                data-testid="trade-coin-input"
                inputMode="numeric"
                value={coinText}
                onChange={(e) => setCoinText(e.target.value)}
                placeholder="Coin to offer"
                className="h-8 w-40 text-sm"
              />
              <Button
                size="sm"
                variant="outline"
                disabled={setCoin.isPending || parseNonNegativeAmount(coinText) === null}
                onClick={() => {
                  const amount = parseNonNegativeAmount(coinText);
                  if (amount === null) return;
                  runMutation(() => setCoin.mutateAsync(amount));
                }}
                data-testid="set-trade-coin-button"
              >
                Offer Coin
              </Button>
            </div>

            {stageableItems.length > 0 && (
              <div className="space-y-1">
                <p className="text-sm text-muted-foreground">Stage an item:</p>
                <div className="flex flex-wrap gap-2">
                  {stageableItems.map((item) => (
                    <Button
                      key={item.id}
                      size="sm"
                      variant="secondary"
                      disabled={stage.isPending}
                      onClick={() =>
                        runMutation(() => stage.mutateAsync(item.game_object_id as number))
                      }
                      data-testid={`stage-item-${item.id}`}
                    >
                      {item.display_name}
                    </Button>
                  ))}
                </div>
              </div>
            )}

            <div className="flex gap-2">
              <Button
                size="sm"
                disabled={confirm.isPending || myConfirmed}
                onClick={() => runMutation(() => confirm.mutateAsync())}
                data-testid="confirm-trade-button"
              >
                {renderConfirm()}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={cancel.isPending}
                onClick={() => runMutation(() => cancel.mutateAsync())}
                data-testid="cancel-trade-button"
              >
                Cancel
              </Button>
            </div>
          </>
        )}

        {session.status === 'completed' && (
          <p className="text-sm text-green-600" data-testid="trade-completed">
            Trade complete.
          </p>
        )}
        {session.status === 'cancelled' && (
          <p className="text-sm text-muted-foreground" data-testid="trade-cancelled">
            Trade cancelled.
          </p>
        )}

        {error && (
          <p className="text-sm text-destructive" data-testid="trade-error">
            {error}
          </p>
        )}
      </CardContent>
    </Card>
  );
}
