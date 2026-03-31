import { useDeferredValue, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Search, UserPlus, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  inviteToEvent,
  removeInvitation,
  searchOrganizations,
  searchPersonas,
  searchSocieties,
} from '../queries';
import type { EventDetailData, EventInvitation } from '../types';

type InviteTargetType = 'persona' | 'organization' | 'society';

const TARGET_TYPE_LABELS: Record<InviteTargetType, string> = {
  persona: 'Persona',
  organization: 'Organization',
  society: 'Society',
};

const SEARCH_FNS: Record<InviteTargetType, (q: string) => Promise<{ id: number; name: string }[]>> =
  {
    persona: searchPersonas,
    organization: searchOrganizations,
    society: searchSocieties,
  };

interface EventInvitationsProps {
  event: EventDetailData;
  canManage: boolean;
}

export function EventInvitations({ event, canManage }: EventInvitationsProps) {
  const queryClient = useQueryClient();
  const [searchQuery, setSearchQuery] = useState('');
  const deferredQuery = useDeferredValue(searchQuery);
  const [showSearch, setShowSearch] = useState(false);
  const [targetType, setTargetType] = useState<InviteTargetType>('persona');

  const { data: searchResults = [] } = useQuery({
    queryKey: [`${targetType}-search`, deferredQuery],
    queryFn: () => SEARCH_FNS[targetType](deferredQuery),
    enabled: deferredQuery.length >= 2,
    staleTime: 30_000,
  });

  const inviteMutation = useMutation({
    mutationFn: ({ type, id }: { type: InviteTargetType; id: number }) =>
      inviteToEvent(event.id, type, id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', String(event.id)] });
      setSearchQuery('');
      setShowSearch(false);
      toast.success('Invitation sent');
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const removeMutation = useMutation({
    mutationFn: (invitationId: number) => removeInvitation(invitationId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', String(event.id)] });
      toast.success('Invitation removed');
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  // Filter out already-invited targets of the current type
  const alreadyInvitedIds = new Set(
    event.invitations
      .filter((inv) => inv.target_type === targetType)
      .map((inv) => {
        if (targetType === 'persona') return inv.target_persona;
        if (targetType === 'organization') return inv.target_organization;
        return inv.target_society;
      })
  );
  const filteredResults = searchResults.filter((r) => !alreadyInvitedIds.has(r.id));

  const closeSearch = () => {
    setShowSearch(false);
    setSearchQuery('');
    setTargetType('persona');
  };

  if (!canManage && event.invitations.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-base">
            <UserPlus className="h-4 w-4" />
            Invitations ({event.invitations.length})
          </CardTitle>
          {canManage && !showSearch && (
            <Button variant="outline" size="sm" onClick={() => setShowSearch(true)}>
              Invite
            </Button>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {showSearch && (
          <div className="space-y-2">
            <div className="flex gap-1">
              {(Object.keys(TARGET_TYPE_LABELS) as InviteTargetType[]).map((type) => (
                <Button
                  key={type}
                  type="button"
                  variant={targetType === type ? 'default' : 'ghost'}
                  size="sm"
                  onClick={() => {
                    setTargetType(type);
                    setSearchQuery('');
                  }}
                >
                  {TARGET_TYPE_LABELS[type]}
                </Button>
              ))}
            </div>
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <Input
                placeholder={`Search ${TARGET_TYPE_LABELS[targetType].toLowerCase()} by name...`}
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-8"
                autoFocus
              />
            </div>
            {filteredResults.length > 0 && (
              <ul className="max-h-40 overflow-y-auto rounded-md border">
                {filteredResults.map((result) => (
                  <li key={result.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-3 py-2 text-sm hover:bg-accent"
                      onClick={() => inviteMutation.mutate({ type: targetType, id: result.id })}
                      disabled={inviteMutation.isPending}
                    >
                      <span>{result.name}</span>
                      <UserPlus className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
            {deferredQuery.length >= 2 && filteredResults.length === 0 && (
              <p className="text-center text-sm text-muted-foreground">
                No {TARGET_TYPE_LABELS[targetType].toLowerCase()}s found
              </p>
            )}
            <Button variant="ghost" size="sm" onClick={closeSearch}>
              Cancel
            </Button>
          </div>
        )}

        {event.invitations.length > 0 ? (
          <ul className="space-y-1">
            {event.invitations.map((inv: EventInvitation) => (
              <li key={inv.id} className="flex items-center justify-between text-sm">
                <div className="flex items-center gap-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs capitalize">
                    {inv.target_type}
                  </span>
                  <span>{inv.target_name || '(deleted)'}</span>
                </div>
                {canManage && (
                  <button
                    type="button"
                    onClick={() => removeMutation.mutate(inv.id)}
                    disabled={removeMutation.isPending}
                    aria-label={`Remove invitation for ${inv.target_name || 'unknown'}`}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                  >
                    <X className="h-3.5 w-3.5" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        ) : (
          !showSearch && (
            <p className="text-center text-sm text-muted-foreground">No invitations yet</p>
          )
        )}
      </CardContent>
    </Card>
  );
}
