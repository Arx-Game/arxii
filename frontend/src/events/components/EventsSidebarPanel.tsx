import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Loader2 } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { urls } from '@/utils/urls';
import { fetchEvents } from '../queries';
import { EventCard } from './EventCard';
import { EVENT_STATUS_TABS } from '../types';
import type { EventListItem, PaginatedResponse } from '../types';

export function EventsSidebarPanel() {
  const [status, setStatus] = useState('scheduled');

  const { data, isLoading, isError } = useQuery<PaginatedResponse<EventListItem>>({
    queryKey: ['events-sidebar', { status }],
    queryFn: () => fetchEvents({ status }),
  });

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-3 py-2">
        <Tabs value={status} onValueChange={setStatus}>
          <TabsList className="w-full">
            {EVENT_STATUS_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} className="flex-1 text-xs">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isError ? (
          <p className="px-3 py-4 text-center text-sm text-muted-foreground">
            Failed to load events.
          </p>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : !data?.results?.length ? (
          <p className="px-3 py-4 text-center text-sm text-muted-foreground">
            No {status === 'scheduled' ? 'upcoming' : status} events.
          </p>
        ) : (
          data.results.map((event) => <EventCard key={event.id} event={event} compact />)
        )}
      </div>

      <div className="border-t px-3 py-2">
        <a
          href={urls.eventsList()}
          target="_blank"
          rel="noopener noreferrer"
          className="flex items-center justify-center gap-1 text-xs text-muted-foreground hover:text-foreground"
        >
          View All Events
          <ExternalLink className="h-3 w-3" />
        </a>
      </div>
    </div>
  );
}
