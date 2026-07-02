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
import type { ManagerRoom, RoomBuilderActionKey } from '../types';

interface TenantSectionProps {
  room: ManagerRoom;
  runAction: (key: RoomBuilderActionKey, kwargs: Record<string, unknown>) => void;
}

/** Owner-side tenancy management: who lives here, assign, end. */
export function TenantSection({ room, runAction }: TenantSectionProps) {
  const [term, setTerm] = useState('');
  const search = usePersonaSearchQuery(term);

  const assign = (personaId: number) => {
    runAction('assign_room_tenant', { room_id: room.id, tenant_persona_id: personaId });
    setTerm('');
  };

  return (
    <div className="flex flex-col gap-2" data-testid="tenant-section">
      <h4 className="text-sm font-semibold">Tenants</h4>
      {room.tenancies.length === 0 && (
        <p className="text-xs text-muted-foreground">No one lives here.</p>
      )}
      {room.tenancies.map((tenancy) => (
        <div key={tenancy.id} className="flex items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-1.5">
            {tenancy.tenant_name}
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
                <AlertDialogTitle>End {tenancy.tenant_name}&apos;s tenancy?</AlertDialogTitle>
                <AlertDialogDescription>
                  They lose their standing in this room
                  {tenancy.is_primary_home ? ' — including their primary home' : ''}.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Cancel</AlertDialogCancel>
                <AlertDialogAction
                  onClick={() => runAction('end_room_tenancy', { tenancy_id: tenancy.id })}
                >
                  End tenancy
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        </div>
      ))}
      <Input
        value={term}
        onChange={(event) => setTerm(event.target.value)}
        placeholder="Assign a tenant — search by name…"
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
              onClick={() => assign(persona.id)}
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
