/**
 * "The World" band (#3412 slice 2) — the state-2 general skim: the calendar,
 * upcoming Occasions, and The Crier (gemits) are account-independent
 * ambiance; the persona tidings digest is docked-only (tidings-split
 * ruling — public awareness scopes to the ACTIVE character, never the
 * account, mirrors `TidingsPage`).
 *
 * No month-name helper exists anywhere in the frontend (verified #3412 T3
 * recon) — the calendar renders the clock's raw fields, no invented
 * calendar lore.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plate, PlateHead } from '@/components/folio';
import { EventCard } from '@/events/components/EventCard';
import { fetchEvents } from '@/events/queries';
import type { EventListItem, PaginatedResponse } from '@/events/types';
import { useGemits } from '@/narrative/queries';
import { TidingsFeed } from '@/tidings/components/TidingsFeed';
import { useAppSelector } from '@/store/hooks';
import { useClockQuery } from './queries';

function capitalize(s: string): string {
  return s.length === 0 ? s : s[0].toUpperCase() + s.slice(1);
}

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

function CalendarPlate() {
  const { data: clock } = useClockQuery();

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-2">
        The Calendar
      </PlateHead>
      {clock ? (
        <div className="space-y-1 text-sm">
          <p>
            Year {clock.year}, Month {clock.month}, Day {clock.day} — {pad(clock.hour)}:
            {pad(clock.minute)}
          </p>
          <p className="text-muted-foreground">
            {capitalize(clock.season)}, {capitalize(clock.phase)}
            {clock.paused && ' · Paused'}
          </p>
        </div>
      ) : (
        // PLACEHOLDER copy
        <p className="text-sm text-muted-foreground">The clock is quiet.</p>
      )}
    </Plate>
  );
}

function OccasionsPlate() {
  const { data } = useQuery<PaginatedResponse<EventListItem>>({
    queryKey: ['events', { upcoming: 'true' }],
    queryFn: () => fetchEvents({ upcoming: 'true' }),
  });
  const events = data?.results ?? [];

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-2">
        Occasions
      </PlateHead>
      {events.length === 0 ? (
        <p className="text-sm text-muted-foreground">Nothing upcoming. How indolent.</p>
      ) : (
        <div className="divide-y">
          {events.slice(0, 5).map((event) => (
            <EventCard key={event.id} event={event} compact />
          ))}
        </div>
      )}
      <Link to="/events" className="mt-2 inline-block text-sm hover:underline">
        All occasions →
      </Link>
    </Plate>
  );
}

function CrierPlate() {
  const { data } = useGemits({ page: 1 });
  const gemits = data?.results ?? [];

  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-2">
        The Crier
      </PlateHead>
      {gemits.length === 0 ? (
        <p className="text-sm text-muted-foreground">No news. A little unsettling.</p>
      ) : (
        <ul className="space-y-2">
          {gemits.map((gemit) => (
            <li key={gemit.id} className="text-sm">
              <p>{gemit.body}</p>
              <p className="text-xs text-muted-foreground">
                {new Date(gemit.sent_at).toLocaleString()}
              </p>
            </li>
          ))}
        </ul>
      )}
    </Plate>
  );
}

function TidingsDigestPlate({ viewerId }: { viewerId: number }) {
  return (
    <Plate className="p-4">
      <PlateHead as="h2" className="mb-2">
        Your Circles
      </PlateHead>
      <TidingsFeed viewerId={viewerId} />
    </Plate>
  );
}

export function WorldBand() {
  const dockedEntryId = useAppSelector((state) => state.game.activeEntryId);

  return (
    <div className="space-y-4">
      <CalendarPlate />
      <OccasionsPlate />
      <CrierPlate />
      {dockedEntryId != null && <TidingsDigestPlate viewerId={dockedEntryId} />}
    </div>
  );
}
