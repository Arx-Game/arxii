/**
 * "Your Attention" band (#3412 slice 2) — grouped by relatedness (see
 * MEMORY: notifications route by relatedness, never merge). An OOC group
 * (Mail, Boards) always shows first; a per-character group renders only for
 * a character with something pending (tidings, an event invitation, an org
 * membership offer) — a character with nothing pending gets no group at all.
 *
 * Invitation/offer "mine" matching mirrors `EventInvitations.tsx`'s own
 * persona-matching approach (`active_persona_id`/`primary_persona_id`,
 * NOT a full per-character persona fetch) — `EventInvitationFilter` has no
 * response/pending filter (#3412 T1 recon), so invitations are filtered
 * client-side from the flat `GET /api/events/invitations/` list.
 */
import { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { CountChip, Plate, PlateHead } from '@/components/folio';
import { useUnreadMailCount } from '@/mail/queries';
import { fetchMyEventInvitations, respondToInvitation } from '@/events/queries';
import type { EventInvitation } from '@/events/types';
import { usePendingMembershipOffersQuery, useRespondToMembershipOffer } from '@/societies/queries';
import type { OrganizationMembershipOffer } from '@/societies/types';
import type { MyRosterEntry } from '@/roster/types';

const invitationsKey = ['events', 'invitations', 'mine'] as const;

/** `entry.active_persona_id`/`primary_persona_id` -> the owning roster entry (mirrors EventInvitations.tsx). */
function buildPersonaToEntry(characters: MyRosterEntry[]): Map<number, MyRosterEntry> {
  const map = new Map<number, MyRosterEntry>();
  for (const entry of characters) {
    if (entry.active_persona_id != null) map.set(entry.active_persona_id, entry);
    if (entry.primary_persona_id != null) map.set(entry.primary_persona_id, entry);
  }
  return map;
}

function InvitationRow({ invitation }: { invitation: EventInvitation }) {
  const queryClient = useQueryClient();
  const respondMutation = useMutation({
    mutationFn: (response: 'accept' | 'decline') => respondToInvitation(invitation.id, response),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: invitationsKey }).catch(() => {});
      toast.success('Your RSVP was sent');
    },
    onError: (err: Error) => toast.error(err.message),
  });

  return (
    <li className="flex items-center justify-between gap-2 py-1 text-sm">
      {/* PLACEHOLDER copy */}
      <span>Invited: {invitation.target_name || 'an event'}</span>
      <span className="flex gap-1">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-6 rounded-none px-2 text-xs"
          disabled={respondMutation.isPending}
          onClick={() => respondMutation.mutate('accept')}
        >
          Accept
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 rounded-none px-2 text-xs"
          disabled={respondMutation.isPending}
          onClick={() => respondMutation.mutate('decline')}
        >
          Decline
        </Button>
      </span>
    </li>
  );
}

function OfferRow({ offer }: { offer: OrganizationMembershipOffer }) {
  const respondMutation = useRespondToMembershipOffer();

  return (
    <li className="flex items-center justify-between gap-2 py-1 text-sm">
      {/* PLACEHOLDER copy */}
      <span>Offer to join {offer.organization_name}</span>
      <span className="flex gap-1">
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-6 rounded-none px-2 text-xs"
          disabled={respondMutation.isPending}
          onClick={() => respondMutation.mutate({ offerId: offer.id, response: 'accept' })}
        >
          Accept
        </Button>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-6 rounded-none px-2 text-xs"
          disabled={respondMutation.isPending}
          onClick={() => respondMutation.mutate({ offerId: offer.id, response: 'decline' })}
        >
          Decline
        </Button>
      </span>
    </li>
  );
}

export function AttentionBand({ characters }: { characters: MyRosterEntry[] }) {
  const unreadMail = useUnreadMailCount();

  const { data: invitationsPage } = useQuery({
    queryKey: invitationsKey,
    queryFn: fetchMyEventInvitations,
  });
  const { data: offersPage } = usePendingMembershipOffersQuery();

  const personaToEntry = useMemo(() => buildPersonaToEntry(characters), [characters]);

  const invitationsByEntry = useMemo(() => {
    const map = new Map<number, EventInvitation[]>();
    for (const inv of invitationsPage?.results ?? []) {
      if (
        inv.response !== 'pending' ||
        inv.target_type !== 'persona' ||
        inv.target_persona == null
      ) {
        continue;
      }
      const entry = personaToEntry.get(inv.target_persona);
      if (!entry) continue;
      const list = map.get(entry.id) ?? [];
      list.push(inv);
      map.set(entry.id, list);
    }
    return map;
  }, [invitationsPage, personaToEntry]);

  const offersByEntry = useMemo(() => {
    const map = new Map<number, OrganizationMembershipOffer[]>();
    for (const offer of offersPage?.results ?? []) {
      if (offer.to_persona == null) continue;
      const entry = personaToEntry.get(offer.to_persona);
      if (!entry) continue;
      const list = map.get(entry.id) ?? [];
      list.push(offer);
      map.set(entry.id, list);
    }
    return map;
  }, [offersPage, personaToEntry]);

  const characterGroups = characters.filter((entry) => {
    const invites = invitationsByEntry.get(entry.id) ?? [];
    const offers = offersByEntry.get(entry.id) ?? [];
    return entry.unread_narrative_count > 0 || invites.length > 0 || offers.length > 0;
  });

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-3">
        Your Attention
      </PlateHead>

      <div className="space-y-1 border-b pb-3">
        <div className="flex items-center justify-between text-sm">
          <Link to="/profile/mail" className="hover:underline">
            Mail
          </Link>
          <CountChip count={unreadMail} label="unread messages" />
        </div>
        <div className="flex items-center justify-between text-sm">
          {/* PLACEHOLDER destination — no global boards index exists yet; boards live
              in-world (room/org boards), so this points there for now (#3412 T3 flag). */}
          <Link to="/game" className="hover:underline">
            The boards
          </Link>
        </div>
      </div>

      {characterGroups.length === 0 ? (
        // PLACEHOLDER copy
        <p className="pt-3 text-sm text-muted-foreground">All is tended, for now.</p>
      ) : (
        <div className="space-y-4 pt-3">
          {characterGroups.map((entry) => {
            const invites = invitationsByEntry.get(entry.id) ?? [];
            const offers = offersByEntry.get(entry.id) ?? [];
            return (
              <div key={entry.id}>
                <PlateHead as="h3" className="mb-1 text-[0.7rem]">
                  {entry.name}
                </PlateHead>
                <ul className="divide-y">
                  {entry.unread_narrative_count > 0 && (
                    <li className="flex items-center justify-between py-1 text-sm">
                      <Link to="/tidings" className="hover:underline">
                        Tidings
                      </Link>
                      <CountChip count={entry.unread_narrative_count} label="tidings waiting" />
                    </li>
                  )}
                  {invites.map((inv) => (
                    <InvitationRow key={inv.id} invitation={inv} />
                  ))}
                  {offers.map((offer) => (
                    <OfferRow key={offer.id} offer={offer} />
                  ))}
                </ul>
              </div>
            );
          })}
        </div>
      )}
    </Plate>
  );
}
