/**
 * Write a missive (#3289): a fresh letter (To by persona search, or fixed when opened
 * from the character card) or a reply to one in the list. Dispatches `send_missive` /
 * `reply_missive` for the acting character.
 *
 * The form mounts only while the dialog is open, so the persona and inventory reads
 * run only when someone is writing.
 */
import { useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useCharacterPersonasQuery } from '@/game/personaQueries';
import { useQuery } from '@tanstack/react-query';
import { listInventory } from '@/inventory/api';
import { inventoryKeys } from '@/inventory/hooks/useInventory';
import { parseCoppers } from '@/lib/currency';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { useMissiveAction } from '../queries';
import type { Missive } from '../types';

export interface MissiveRecipient {
  id: number;
  name: string;
}

interface MissiveComposeDialogProps {
  open: boolean;
  onClose: () => void;
  /** The acting character (ObjectDB id; the same pk as its CharacterSheet). */
  characterId: number;
  /** The face the character wears now; the default sender for a fresh letter. */
  activePersonaId?: number | null;
  /** Fixed addressee (from the character card). */
  recipient?: MissiveRecipient | null;
  /** The letter being answered. */
  replyTo?: Missive | null;
}

function dialogTitle(recipient?: MissiveRecipient | null, replyTo?: Missive | null): string {
  if (replyTo) return `Reply to ${replyTo.counterpart_name}`;
  if (recipient) return `Missive to ${recipient.name}`;
  return 'New missive';
}

export function MissiveComposeDialog({
  open,
  onClose,
  characterId,
  activePersonaId = null,
  recipient = null,
  replyTo = null,
}: MissiveComposeDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={(isOpen) => {
        if (!isOpen) onClose();
      }}
    >
      <DialogContent {...NO_DESCRIPTION}>
        <DialogHeader>
          <DialogTitle>{dialogTitle(recipient, replyTo)}</DialogTitle>
        </DialogHeader>
        {open && (
          <ComposeForm
            characterId={characterId}
            activePersonaId={activePersonaId}
            recipient={recipient}
            replyTo={replyTo}
            onSent={onClose}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

interface ComposeFormProps {
  characterId: number;
  activePersonaId: number | null;
  recipient: MissiveRecipient | null;
  replyTo: Missive | null;
  onSent: () => void;
}

const SELECT_CLASS =
  'flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm';

function ComposeForm({
  characterId,
  activePersonaId,
  recipient,
  replyTo,
  onSent,
}: ComposeFormProps) {
  const { data: personas = [] } = useCharacterPersonasQuery(characterId);
  // Not Wardrobe's `useInventory`: that one throws to the route boundary, and a failed
  // read here should only hide the Items field.
  const { data: inventory = [] } = useQuery({
    queryKey: inventoryKeys.inventory(characterId),
    queryFn: () => listInventory(characterId),
    throwOnError: false,
  });
  const action = useMissiveAction(characterId);

  const [to, setTo] = useState<MissiveRecipient | null>(recipient);
  const [term, setTerm] = useState('');
  const { results } = usePersonaSearch(term, { enabled: !recipient && !replyTo && !to });
  const [chosenFrom, setChosenFrom] = useState<number | null>(null);
  const [body, setBody] = useState('');
  const [coin, setCoin] = useState('');
  const [itemIds, setItemIds] = useState<number[]>([]);

  const defaultFrom =
    replyTo?.own_persona_id ??
    activePersonaId ??
    personas.find((p) => p.persona_type === 'primary')?.id ??
    personas[0]?.id ??
    null;
  const fromId = chosenFrom ?? defaultFrom;

  const toggleItem = (id: number) =>
    setItemIds((ids) => (ids.includes(id) ? ids.filter((i) => i !== id) : [...ids, id]));

  const coinAmount = coin.trim() === '' ? null : parseCoppers(coin);
  const coinInvalid = coin.trim() !== '' && coinAmount === null;
  const canSend = body.trim().length > 0 && (replyTo !== null || to !== null) && !coinInvalid;

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    if (!canSend) return;
    const kwargs: Record<string, unknown> = { body };
    if (fromId != null) kwargs.sender_persona_id = fromId;
    if (coinAmount !== null) kwargs.coin_amount = coinAmount;
    if (itemIds.length > 0) kwargs.item_ids = itemIds;
    if (replyTo) {
      kwargs.missive_id = replyTo.id;
    } else if (to) {
      kwargs.recipient_persona_id = to.id;
    }
    action.mutate(
      { key: replyTo ? 'reply_missive' : 'send_missive', kwargs },
      {
        onSuccess: ({ message }) => {
          if (message) toast.success(message);
          onSent();
        },
        onError: (err) => toast.error(err.message),
      }
    );
  };

  const renderTo = () => {
    if (replyTo || recipient) return null;
    if (to) {
      return (
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium">{to.name}</span>
          <Button type="button" variant="ghost" size="sm" onClick={() => setTo(null)}>
            Change
          </Button>
        </div>
      );
    }
    return (
      <div className="space-y-1">
        <Input
          id="missive-to"
          value={term}
          onChange={(e) => setTerm(e.target.value)}
          autoComplete="off"
        />
        {results.length > 0 && (
          <ul className="rounded border">
            {results.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  className="w-full px-3 py-1 text-left text-sm hover:bg-accent"
                  onClick={() => {
                    setTo({ id: p.id, name: p.name });
                    setTerm('');
                  }}
                >
                  {p.name}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  const toField = renderTo();

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {toField && (
        <div className="space-y-1">
          {/* The label points at the search box only while it is mounted. */}
          <Label htmlFor={to ? undefined : 'missive-to'}>To</Label>
          {toField}
        </div>
      )}
      {personas.length > 1 && (
        <div className="space-y-1">
          <Label htmlFor="missive-from">From</Label>
          <select
            id="missive-from"
            className={SELECT_CLASS}
            value={fromId ?? ''}
            onChange={(e) => setChosenFrom(Number(e.target.value))}
          >
            {personas.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="space-y-1">
        <Label htmlFor="missive-body">Message</Label>
        <Textarea
          id="missive-body"
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={6}
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="missive-coin">Coin</Label>
        <Input
          id="missive-coin"
          placeholder="1g 2s 3c"
          aria-invalid={coinInvalid}
          value={coin}
          onChange={(e) => setCoin(e.target.value)}
        />
      </div>
      {inventory.length > 0 && (
        <fieldset className="space-y-1">
          <legend className="text-sm font-medium">Items</legend>
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {inventory.map((item) => (
              <label key={item.id} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={itemIds.includes(item.id)}
                  onChange={() => toggleItem(item.id)}
                />
                {item.display_name}
              </label>
            ))}
          </div>
        </fieldset>
      )}
      <div className="flex justify-end">
        <Button type="submit" disabled={!canSend || action.isPending}>
          Send
        </Button>
      </div>
    </form>
  );
}
