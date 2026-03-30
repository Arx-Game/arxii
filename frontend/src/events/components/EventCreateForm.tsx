import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { urls } from '@/utils/urls';
import { createEvent } from '../queries';
import { TIME_PHASES, toLocalDatetimeValue } from '../types';
import { AreaDrilldownPicker } from './AreaDrilldownPicker';
import type { EventCreateData, TimePhase } from '../types';

export function EventCreateForm() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [locationId, setLocationId] = useState<number | null>(null);
  const [isPublic, setIsPublic] = useState(true);
  const [scheduledRealTime, setScheduledRealTime] = useState('');
  const [timePhase, setTimePhase] = useState<TimePhase>('day');

  const mutation = useMutation({
    mutationFn: (data: EventCreateData) => createEvent(data),
    onSuccess: (event) => {
      queryClient.invalidateQueries({ queryKey: ['events'] });
      toast.success('Event created');
      navigate(urls.event(event.id));
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !locationId || !scheduledRealTime) return;

    mutation.mutate({
      name: name.trim(),
      description: description.trim(),
      location: locationId,
      is_public: isPublic,
      scheduled_real_time: new Date(scheduledRealTime).toISOString(),
      time_phase: timePhase,
    });
  };

  const isValid = name.trim() && locationId && scheduledRealTime;

  return (
    <form onSubmit={handleSubmit} className="space-y-6">
      <div className="space-y-2">
        <Label htmlFor="event-name">Event Name *</Label>
        <Input
          id="event-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="The Duchess's Coronation Ball"
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="event-desc">Description</Label>
        <Textarea
          id="event-desc"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What is this event about?"
          rows={3}
        />
      </div>

      <div className="space-y-2">
        <Label>Location *</Label>
        <AreaDrilldownPicker value={locationId} onChange={(id) => setLocationId(id)} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="event-time">Scheduled Time (OOC) *</Label>
        <Input
          id="event-time"
          type="datetime-local"
          value={scheduledRealTime}
          onChange={(e) => setScheduledRealTime(e.target.value)}
          min={toLocalDatetimeValue(new Date().toISOString())}
          required
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="event-phase">Time of Day (IC)</Label>
        <select
          id="event-phase"
          value={timePhase}
          onChange={(e) => setTimePhase(e.target.value as TimePhase)}
          className="w-full rounded-md border bg-background px-3 py-2 text-sm"
        >
          {TIME_PHASES.map((p) => (
            <option key={p.value} value={p.value}>
              {p.label}
            </option>
          ))}
        </select>
      </div>

      <div className="flex items-center gap-3">
        <Switch id="event-public" checked={isPublic} onCheckedChange={setIsPublic} />
        <Label htmlFor="event-public">Public event (visible to everyone)</Label>
      </div>

      <div className="flex gap-3">
        <Button type="submit" disabled={!isValid || mutation.isPending}>
          {mutation.isPending ? 'Creating...' : 'Create Event'}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate(urls.eventsList())}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
