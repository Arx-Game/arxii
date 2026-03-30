import { useParams, Link, Navigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Loader2 } from 'lucide-react';
import { useAccount } from '@/store/hooks';
import { urls } from '@/utils/urls';
import { fetchEvent } from '../queries';
import { EventEditForm } from '../components/EventEditForm';
import { EVENT_STATUS } from '../types';

export function EventEditPage() {
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
  const canEdit = event.is_host || isStaff;
  const isEditable = event.status === EVENT_STATUS.DRAFT || event.status === EVENT_STATUS.SCHEDULED;

  if (!canEdit || !isEditable) {
    return <Navigate to={urls.event(event.id)} replace />;
  }

  return (
    <div className="container mx-auto max-w-2xl px-4 py-8">
      <Link
        to={urls.event(event.id)}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to event
      </Link>
      <h1 className="mb-6 text-2xl font-bold">Edit Event</h1>
      <EventEditForm event={event} />
    </div>
  );
}
