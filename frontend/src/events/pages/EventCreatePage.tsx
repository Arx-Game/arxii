import { EventCreateForm } from '../components/EventCreateForm';

export function EventCreatePage() {
  return (
    <div className="container mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Create Event</h1>
      <EventCreateForm />
    </div>
  );
}
