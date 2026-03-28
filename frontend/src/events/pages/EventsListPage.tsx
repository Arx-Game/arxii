import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { CalendarPlus, Loader2, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { useAccount } from '@/store/hooks';
import { urls } from '@/utils/urls';
import { fetchEvents } from '../queries';
import { EventCard } from '../components/EventCard';
import type { EventListItem, PaginatedResponse } from '../types';

const STATUS_TABS = [
  { value: 'scheduled', label: 'Upcoming' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Past' },
] as const;

export function EventsListPage() {
  const account = useAccount();
  const [status, setStatus] = useState('scheduled');
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [page, setPage] = useState(1);

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 300);
    return () => clearTimeout(timer);
  }, [search]);

  const params: Record<string, string> = { status, page: String(page) };
  if (debouncedSearch) params.search = debouncedSearch;

  const { data, isLoading, isError } = useQuery<PaginatedResponse<EventListItem>>({
    queryKey: ['events', params],
    queryFn: () => fetchEvents(params),
  });

  return (
    <div className="container mx-auto px-4 py-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold">Events</h1>
        {account && (
          <Link to={urls.eventCreate()}>
            <Button>
              <CalendarPlus className="mr-2 h-4 w-4" />
              Create Event
            </Button>
          </Link>
        )}
      </div>

      <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-center">
        <Tabs
          value={status}
          onValueChange={(v) => {
            setStatus(v);
            setPage(1);
          }}
        >
          <TabsList>
            {STATUS_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value}>
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>

        <div className="relative flex-1 sm:max-w-xs">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search events..."
            className="pl-9"
          />
        </div>
      </div>

      {isError ? (
        <p className="py-8 text-center text-muted-foreground">Failed to load events.</p>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </div>
      ) : !data?.results?.length ? (
        <p className="py-8 text-center text-muted-foreground">
          {debouncedSearch
            ? `No events found for "${debouncedSearch}".`
            : `No ${status === 'scheduled' ? 'upcoming' : status} events.`}
        </p>
      ) : (
        <>
          <div className="space-y-3">
            {data.results.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
          </div>

          {data.num_pages > 1 && (
            <div className="mt-6 flex items-center justify-center gap-2">
              <Button
                variant="outline"
                size="sm"
                disabled={page === 1}
                onClick={() => setPage((p) => p - 1)}
              >
                Previous
              </Button>
              <span className="text-sm text-muted-foreground">
                Page {data.current_page} of {data.num_pages}
              </span>
              <Button
                variant="outline"
                size="sm"
                disabled={page >= data.num_pages}
                onClick={() => setPage((p) => p + 1)}
              >
                Next
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
