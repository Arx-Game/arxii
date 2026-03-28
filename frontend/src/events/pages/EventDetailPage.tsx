import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useAccount } from '@/store/hooks';
import { urls } from '@/utils/urls';
import { fetchEvent } from '../queries';
import { EventDetail } from '../components/EventDetail';

export function EventDetailPage() {
  const { id = '' } = useParams();
  const account = useAccount();

  const {
    data: event,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['event', id],
    queryFn: () => fetchEvent(id),
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-16">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error || !event) {
    return (
      <div className="container mx-auto px-4 py-8 text-center">
        <p className="text-muted-foreground">Event not found.</p>
        <Link to={urls.eventsList()} className="mt-2 text-sm text-blue-500 hover:underline">
          Back to events
        </Link>
      </div>
    );
  }

  const isStaff = account?.is_staff ?? false;

  return (
    <div className="container mx-auto max-w-3xl px-4 py-8">
      <Link
        to={urls.eventsList()}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to events
      </Link>
      <EventDetail event={event} isStaff={isStaff} />
    </div>
  );
}
