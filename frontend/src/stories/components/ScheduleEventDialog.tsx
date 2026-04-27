/**
 * ScheduleEventDialog — GM action to create an Event from a session request.
 *
 * Opened from AssignedSessionRequestRow for OPEN session requests.
 *
 * Room selection reuses AreaDrilldownPicker from the events module.
 * Persona selection uses a text search against /api/personas/ — a full
 * PersonaSelector component is a candidate for extraction in a later wave
 * once this pattern is reused elsewhere.
 *
 * Decision: No time_phase field — the CreateEventBody type from stories/types.ts
 * maps to the CreateEventFromSessionRequestInputSerializer which only requires
 * the six fields listed here (name, scheduled_real_time, host_persona,
 * location_id, description, is_public). time_phase is an events-app concern
 * not surfaced in the session-request action.
 */

import { useState, useEffect, useRef } from 'react';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import { AreaDrilldownPicker } from '@/events/components/AreaDrilldownPicker';
import { searchPersonas } from '@/events/queries';
import { toLocalDatetimeValue } from '@/events/types';
import { useCreateEventFromSessionRequest } from '../queries';
import type { GMQueueAssignedRequest } from '../types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

interface ScheduleEventDialogProps {
  request: GMQueueAssignedRequest;
}

// ---------------------------------------------------------------------------
// DRF error shapes
// ---------------------------------------------------------------------------

interface DRFFieldErrors {
  name?: string[];
  scheduled_real_time?: string[];
  host_persona?: string[];
  location_id?: string[];
  description?: string[];
  is_public?: string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Persona search result shape
// ---------------------------------------------------------------------------

interface PersonaOption {
  id: number;
  name: string;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ScheduleEventDialog({ request }: ScheduleEventDialogProps) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState(`${request.story_title} — ${request.episode_title}`);
  const [scheduledRealTime, setScheduledRealTime] = useState('');
  const [locationId, setLocationId] = useState<number | null>(null);
  const [isPublic, setIsPublic] = useState(true);
  const [description, setDescription] = useState('');
  const [fieldErrors, setFieldErrors] = useState<DRFFieldErrors>({});

  // Persona search state
  const [personaQuery, setPersonaQuery] = useState('');
  const [personaResults, setPersonaResults] = useState<PersonaOption[]>([]);
  const [selectedPersona, setSelectedPersona] = useState<PersonaOption | null>(null);
  const [personaSearching, setPersonaSearching] = useState(false);
  const personaDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const createMutation = useCreateEventFromSessionRequest();

  // Debounced persona search
  useEffect(() => {
    if (personaDebounceRef.current) clearTimeout(personaDebounceRef.current);
    if (personaQuery.trim().length < 2) {
      setPersonaResults([]);
      return;
    }
    personaDebounceRef.current = setTimeout(() => {
      setPersonaSearching(true);
      searchPersonas(personaQuery.trim())
        .then((results) => setPersonaResults(results))
        .catch(() => setPersonaResults([]))
        .finally(() => setPersonaSearching(false));
    }, 300);
  }, [personaQuery]);

  function resetForm() {
    setName(`${request.story_title} — ${request.episode_title}`);
    setScheduledRealTime('');
    setLocationId(null);
    setIsPublic(true);
    setDescription('');
    setFieldErrors({});
    setPersonaQuery('');
    setPersonaResults([]);
    setSelectedPersona(null);
  }

  function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) resetForm();
  }

  const isValid =
    name.trim().length > 0 && scheduledRealTime && locationId !== null && selectedPersona !== null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!isValid || selectedPersona === null || locationId === null) return;
    setFieldErrors({});

    createMutation.mutate(
      {
        requestId: request.session_request_id,
        name: name.trim(),
        scheduled_real_time: new Date(scheduledRealTime).toISOString(),
        host_persona: selectedPersona.id,
        location_id: locationId,
        description: description.trim() || undefined,
        is_public: isPublic,
      },
      {
        onSuccess: (updatedRequest) => {
          setOpen(false);
          resetForm();
          const eventId = updatedRequest.event;
          if (eventId !== null && eventId !== undefined) {
            toast.success(`Event scheduled — event #${String(eventId)}`);
          } else {
            toast.success('Event scheduled');
          }
        },
        onError: (err: unknown) => {
          if (err && typeof err === 'object' && 'response' in err) {
            const response = (err as { response?: Response }).response;
            if (response) {
              void response
                .json()
                .then((data: unknown) => {
                  if (data && typeof data === 'object') {
                    setFieldErrors(data as DRFFieldErrors);
                  }
                })
                .catch(() => {
                  toast.error('An error occurred. Please try again.');
                });
              return;
            }
          }
          const message =
            err instanceof Error ? err.message : 'An error occurred. Please try again.';
          toast.error(message);
        },
      }
    );
  }

  const nonFieldErrors = fieldErrors.non_field_errors ?? [];
  const detailError = fieldErrors.detail ?? '';
  const minDatetime = toLocalDatetimeValue(new Date().toISOString());

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="default" size="sm">
          Schedule
        </Button>
      </DialogTrigger>

      <DialogContent className="sm:max-w-lg">
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>Schedule session for: {request.episode_title}</DialogTitle>
            <DialogDescription>{request.story_title}</DialogDescription>
          </DialogHeader>

          {/* Non-field / global error banner */}
          {(nonFieldErrors.length > 0 || detailError) && (
            <div className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {detailError && <p>{detailError}</p>}
              {nonFieldErrors.map((msg, i) => (
                <p key={i}>{msg}</p>
              ))}
            </div>
          )}

          <div className="mt-4 grid gap-4">
            {/* Event name */}
            <div className="space-y-1.5">
              <Label htmlFor="schedule-name">Event name *</Label>
              <Input
                id="schedule-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
              {fieldErrors.name && fieldErrors.name.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.name.join(' ')}</p>
              )}
            </div>

            {/* Scheduled real time */}
            <div className="space-y-1.5">
              <Label htmlFor="schedule-time">Scheduled time (OOC) *</Label>
              <Input
                id="schedule-time"
                type="datetime-local"
                value={scheduledRealTime}
                onChange={(e) => setScheduledRealTime(e.target.value)}
                min={minDatetime}
                required
              />
              {fieldErrors.scheduled_real_time && fieldErrors.scheduled_real_time.length > 0 && (
                <p className="text-xs text-destructive">
                  {fieldErrors.scheduled_real_time.join(' ')}
                </p>
              )}
            </div>

            {/* Host persona search */}
            <div className="space-y-1.5">
              <Label htmlFor="schedule-persona">Host persona *</Label>
              {selectedPersona ? (
                <div className="flex items-center gap-2 rounded-md border p-2">
                  <span className="flex-1 text-sm">{selectedPersona.name}</span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => {
                      setSelectedPersona(null);
                      setPersonaQuery('');
                    }}
                  >
                    Change
                  </Button>
                </div>
              ) : (
                <div className="relative">
                  <Input
                    id="schedule-persona"
                    placeholder="Search for a persona…"
                    value={personaQuery}
                    onChange={(e) => setPersonaQuery(e.target.value)}
                    autoComplete="off"
                  />
                  {personaSearching && (
                    <p className="mt-1 text-xs text-muted-foreground">Searching…</p>
                  )}
                  {personaResults.length > 0 && (
                    <div className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-md">
                      {personaResults.map((p) => (
                        <button
                          key={p.id}
                          type="button"
                          className="w-full px-3 py-2 text-left text-sm hover:bg-accent"
                          onClick={() => {
                            setSelectedPersona(p);
                            setPersonaQuery('');
                            setPersonaResults([]);
                          }}
                        >
                          {p.name}
                        </button>
                      ))}
                    </div>
                  )}
                  {!personaSearching &&
                    personaQuery.trim().length >= 2 &&
                    personaResults.length === 0 && (
                      <p className="mt-1 text-xs text-muted-foreground">No personas found.</p>
                    )}
                </div>
              )}
              {fieldErrors.host_persona && fieldErrors.host_persona.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.host_persona.join(' ')}</p>
              )}
            </div>

            {/* Location */}
            <div className="space-y-1.5">
              <Label>Location *</Label>
              <AreaDrilldownPicker value={locationId} onChange={(id) => setLocationId(id)} />
              {fieldErrors.location_id && fieldErrors.location_id.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.location_id.join(' ')}</p>
              )}
            </div>

            {/* Description */}
            <div className="space-y-1.5">
              <Label htmlFor="schedule-description">
                Description <span className="text-muted-foreground">(optional)</span>
              </Label>
              <Textarea
                id="schedule-description"
                placeholder="What is this session about?"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={3}
              />
              {fieldErrors.description && fieldErrors.description.length > 0 && (
                <p className="text-xs text-destructive">{fieldErrors.description.join(' ')}</p>
              )}
            </div>

            {/* Public */}
            <div className="flex items-center gap-3">
              <Switch id="schedule-public" checked={isPublic} onCheckedChange={setIsPublic} />
              <Label htmlFor="schedule-public">Public event (visible to everyone)</Label>
            </div>
          </div>

          <DialogFooter className="mt-6">
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={createMutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={createMutation.isPending || !isValid}>
              {createMutation.isPending ? 'Scheduling…' : 'Schedule Event'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
