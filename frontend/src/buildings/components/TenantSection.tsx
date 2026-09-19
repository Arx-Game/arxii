import { useState } from 'react';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';

import { usePersonaSearchQuery } from '../queries';
import type { ManagerRoom, ManagerTenancy, RoomBuilderActionKey } from '../types';

type GrantKind = ManagerTenancy['kind'];

/**
 * The three rungs a player can hand out here (#3902), in ladder order. The labels
 * are what the game calls them in play: a guest holds a "key", not a "guest grant".
 * Who may actually give each one is the service's call; the UI offers all three and
 * shows the refusal the action returns.
 */
const GRANT_KINDS: { kind: GrantKind; label: string; verb: string }[] = [
  { kind: 'guest', label: 'Key', verb: 'Give a key to' },
  { kind: 'tenant', label: 'Tenant', verb: 'Assign a tenant' },
  { kind: 'trustee', label: 'Trustee', verb: 'Appoint a trustee' },
];

const RUNG_BADGE: Record<GrantKind, string> = {
  guest: 'key',
  tenant: 'tenant',
  trustee: 'trustee',
};

interface TenantSectionProps {
  room: ManagerRoom;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/** Who holds what here: keys, tenancies and trusteeships; grant one, take one back. */
export function TenantSection({ room, runAction }: TenantSectionProps) {
  const [term, setTerm] = useState('');
  const [kind, setKind] = useState<GrantKind>('tenant');
  const search = usePersonaSearchQuery(term);
  const chosen = GRANT_KINDS.find((entry) => entry.kind === kind) ?? GRANT_KINDS[1];

  const grant = (personaId: number) => {
    runAction('assign_room_tenant', { room_id: room.id, tenant_persona_id: personaId, kind });
    setTerm('');
  };

  return (
    <div className="flex flex-col gap-2" data-testid="tenant-section">
      <h4 className="text-sm font-semibold">Tenants and keys</h4>
      {room.tenancies.length === 0 && (
        <p className="text-xs text-muted-foreground">No one holds a grant here.</p>
      )}
      {room.tenancies.map((tenancy) => (
        <div key={tenancy.id} className="flex items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-1.5">
            {tenancy.tenant_name}
            <Badge variant="outline">{RUNG_BADGE[tenancy.kind]}</Badge>
            {tenancy.is_primary_home && <Badge variant="secondary">home</Badge>}
          </span>
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="ghost" size="sm">
                End
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>
                  {tenancy.kind === 'guest'
                    ? `Take back ${tenancy.tenant_name}'s key?`
                    : `End ${tenancy.tenant_name}'s ${RUNG_BADGE[tenancy.kind]} standing?`}
                </AlertDialogTitle>
                <AlertDialogDescription>
                  They lose their standing in this room
                  {tenancy.is_primary_home ? ', including their primary home' : ''}.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => runAction('end_room_tenancy', { tenancy_id: tenancy.id })}
                >
                  {tenancy.kind === 'guest' ? 'Take back the key' : 'End it'}
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ))}
      <div className="flex flex-wrap gap-1" role="radiogroup" aria-label="What to grant">
        {GRANT_KINDS.map((entry) => (
          <Button
            key={entry.kind}
            type="button"
            variant={entry.kind === kind ? 'secondary' : 'ghost'}
            size="sm"
            role="radio"
            aria-checked={entry.kind === kind}
            onClick={() => setKind(entry.kind)}
          >
            {entry.label}
          </Button>
        ))}
      </div>
      <Input
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder={`${chosen.verb}: search by name…`}
        data-testid="tenant-search"
      />
      {term.trim().length >= 2 && (
        <div className="flex flex-col gap-1">
          {(search.data ?? []).slice(0, 6).map((persona) => (
            <Button
              key={persona.id}
              variant="ghost"
              size="sm"
              className="justify-start"
              onClick={() => grant(persona.id)}
            >
              {persona.name}
            </Button>
          ))}
          {search.data && search.data.length === 0 && (
            <p className="text-xs text-muted-foreground">No personas match.</p>
          )}
        </div>
      )}
    </div>
  );
}
