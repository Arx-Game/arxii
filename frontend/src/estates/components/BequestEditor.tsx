import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { usePersonaSearch, useOrganizationSearch } from '@/roster/usePersonaSearch';
import type { Will } from '../estatesQueries';
import type { useWillMutations } from '../estatesQueries';

const KIND_LABELS: Record<string, string> = {
  specific_item: 'A specific item',
  coin_amount: 'A sum of coin',
  all_coin: 'All remaining coin',
  building: 'A building',
  business: 'A business',
  residuary: 'Everything else (residuary)',
};

// Items and businesses are held by characters; organizations cannot receive them.
const PERSONA_ONLY_KINDS = new Set(['specific_item', 'business']);
const TARGET_FIELD: Record<string, 'item' | 'building' | 'business' | null> = {
  specific_item: 'item',
  coin_amount: null,
  all_coin: null,
  building: 'building',
  business: 'business',
  residuary: null,
};

interface BequestEditorProps {
  will: Will;
  frozen: boolean;
  mutations: ReturnType<typeof useWillMutations>;
}

export function BequestEditor({ will, frozen, mutations }: BequestEditorProps) {
  const [kind, setKind] = useState('residuary');
  const [amount, setAmount] = useState('');
  const [targetId, setTargetId] = useState('');
  const [recipientQuery, setRecipientQuery] = useState('');
  const [recipientIsOrg, setRecipientIsOrg] = useState(false);
  const [recipient, setRecipient] = useState<{ id: number; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const targetField = TARGET_FIELD[kind];
  const personaOnly = PERSONA_ONLY_KINDS.has(kind);

  // Race-safe debounced search (2026-07 audit): the old handler awaited the
  // fetch inline with no debounce or ordering guard, and a toggle mid-request
  // could show org results under a persona query. Both hooks are keyed by term;
  // only the one matching the current toggle fetches.
  const { results: personaMatches } = usePersonaSearch(recipientQuery, {
    enabled: !recipientIsOrg,
  });
  const { results: orgMatches } = useOrganizationSearch(recipientQuery, {
    enabled: recipientIsOrg,
  });
  const matches = recipientIsOrg ? orgMatches : personaMatches;

  const search = (query: string) => {
    setRecipientQuery(query);
    setRecipient(null);
  };

  const submit = () => {
    if (!recipient) {
      setError('Pick a recipient first.');
      return;
    }
    setError(null);
    const bequest: Record<string, unknown> = {
      will: will.id,
      kind,
      amount: kind === 'coin_amount' ? Number(amount) || 0 : 0,
    };
    if (targetField) bequest[targetField] = Number(targetId) || null;
    if (recipientIsOrg) bequest.recipient_organization = recipient.id;
    else bequest.recipient_persona = recipient.id;
    mutations.addBequest.mutate(bequest as never, {
      onError: (err: Error) => setError(err.message),
    });
  };

  return (
    <section className="space-y-2">
      <h3 className="text-xl font-semibold">Bequests</h3>
      <ul className="space-y-1">
        {will.bequests.map((b) => (
          <li key={b.id} className="flex items-center justify-between rounded border p-2 text-sm">
            <span>
              {KIND_LABELS[b.kind] ?? b.kind}
              {b.kind === 'coin_amount' ? ` (${b.amount} coppers)` : ''}
            </span>
            {!frozen && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => mutations.removeBequest.mutate(b.id)}
              >
                Remove
              </Button>
            )}
          </li>
        ))}
        {will.bequests.length === 0 && (
          <li className="text-sm text-muted-foreground">No bequests yet.</li>
        )}
      </ul>
      {!frozen && (
        <div className="space-y-2 rounded border p-3">
          <select
            className="w-full rounded border bg-background p-2 text-sm"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              if (PERSONA_ONLY_KINDS.has(e.target.value)) setRecipientIsOrg(false);
            }}
            aria-label="Bequest kind"
          >
            {Object.entries(KIND_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
          {kind === 'coin_amount' && (
            <Input
              type="number"
              placeholder="Coppers"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          )}
          {targetField && (
            <Input
              type="number"
              placeholder={`${targetField} id`}
              value={targetId}
              onChange={(e) => setTargetId(e.target.value)}
            />
          )}
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={recipientIsOrg}
              disabled={personaOnly}
              onChange={(e) => setRecipientIsOrg(e.target.checked)}
            />
            Recipient is an organization
          </label>
          <Input
            placeholder={recipientIsOrg ? 'Search organizations…' : 'Search characters…'}
            value={recipient ? recipient.name : recipientQuery}
            onChange={(e) => void search(e.target.value)}
          />
          {matches.length > 0 && !recipient && (
            <ul className="rounded border text-sm">
              {matches.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className="w-full p-1 text-left hover:bg-accent"
                    onClick={() => {
                      setRecipient(m);
                      setMatches([]);
                    }}
                  >
                    {m.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button size="sm" onClick={submit} disabled={mutations.addBequest.isPending}>
            Add bequest
          </Button>
        </div>
      )}
    </section>
  );
}
