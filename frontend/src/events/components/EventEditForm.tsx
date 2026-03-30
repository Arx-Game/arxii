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
import { updateEvent } from '../queries';
import { TIME_PHASES, toLocalDatetimeValue } from '../types';
import type { EventDetailData, EventUpdateData, TimePhase } from '../types';

interface EventEditFormProps {
  event: EventDetailData;
}

export function EventEditForm({ event }: EventEditFormProps) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [name, setName] = useState(event.name);
  const [description, setDescription] = useState(event.description);
  const [isPublic, setIsPublic] = useState(event.is_public);
  const [scheduledRealTime, setScheduledRealTime] = useState(
    toLocalDatetimeValue(event.scheduled_real_time)
  );
  const [timePhase, setTimePhase] = useState<TimePhase>(event.time_phase);

  const mutation = useMutation({
    mutationFn: (data: EventUpdateData) => updateEvent(String(event.id), data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', String(event.id)] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
      toast.success('Event updated');
      navigate(urls.event(event.id));
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !scheduledRealTime) return;

    mutation.mutate({
      name: name.trim(),
      description: description.trim(),
      is_public: isPublic,
      scheduled_real_time: new Date(scheduledRealTime).toISOString(),
      time_phase: timePhase,
    });
  };

  const isValid = name.trim() && scheduledRealTime;

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
          {mutation.isPending ? 'Saving...' : 'Save Changes'}
        </Button>
        <Button type="button" variant="outline" onClick={() => navigate(urls.event(event.id))}>
          Cancel
        </Button>
      </div>
    </form>
  );
}
