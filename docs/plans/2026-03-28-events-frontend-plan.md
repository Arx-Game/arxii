# Events Frontend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the events frontend — list page, detail page, creation form with area drill-down picker, and game sidebar integration.

**Architecture:** Three standalone pages (`/events`, `/events/:id`, `/events/new`) using React Query for API data, plus a compact Events tab in the game view's right sidebar. Shared components adapt to both contexts via a `compact` prop. Backend additions: Area browsing API for the location picker, RoomProfile.is_public field.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Radix UI (Tabs, Dialog, Select), React Query, Lucide icons, native `<input type="datetime-local">` for date picking.

**Design doc:** `docs/plans/2026-03-28-events-frontend-design.md`

---

### Task 1: Backend — RoomProfile.is_public field

**Files:**
- Modify: `src/evennia_extensions/models.py`

**Step 1: Add is_public field to RoomProfile**

Add after the `area` field:

```python
is_public = models.BooleanField(
    default=True,
    help_text="Whether this room appears in public room listings (e.g., event location picker)",
)
```

**Step 2: Generate and apply migration**

Run: `uv run arx manage makemigrations evennia_extensions`
Run: `uv run arx manage migrate evennia_extensions`

**Step 3: Commit**

```
feat(areas): add is_public field to RoomProfile
```

---

### Task 2: Backend — Area browsing API

**Files:**
- Create: `src/world/areas/views.py`
- Create: `src/world/areas/urls.py`
- Create: `src/world/areas/filters.py`
- Modify: `src/world/areas/serializers.py`
- Modify: `src/web/urls.py`

**Step 1: Create serializers**

Add to `src/world/areas/serializers.py`:

```python
class AreaListSerializer(serializers.ModelSerializer):
    level_display = serializers.CharField(source="get_level_display", read_only=True)
    children_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Area
        fields = ["id", "name", "level", "level_display", "children_count"]
        read_only_fields = fields


class AreaRoomSerializer(serializers.Serializer):
    id = serializers.IntegerField(source="pk")
    name = serializers.CharField(source="objectdb.db_key")
    area_name = serializers.CharField(source="area.name", default="")
```

**Step 2: Create filters**

```python
# src/world/areas/filters.py
import django_filters

from world.areas.models import Area


class AreaFilter(django_filters.FilterSet):
    parent = django_filters.NumberFilter(field_name="parent_id")
    has_parent = django_filters.BooleanFilter(method="filter_has_parent")

    class Meta:
        model = Area
        fields = ["parent", "has_parent"]

    def filter_has_parent(self, queryset, name, value):
        if value is True:
            return queryset.filter(parent__isnull=False)
        if value is False:
            return queryset.filter(parent__isnull=True)
        return queryset
```

**Step 3: Create views**

```python
# src/world/areas/views.py
from django.db.models import Count, QuerySet
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from evennia_extensions.models import RoomProfile
from world.areas.filters import AreaFilter
from world.areas.models import Area
from world.areas.serializers import AreaListSerializer, AreaRoomSerializer


class AreaViewSet(ReadOnlyModelViewSet):
    """Browse the area hierarchy for room selection."""

    serializer_class = AreaListSerializer
    permission_classes = [IsAuthenticatedOrReadOnly]
    filter_backends = [DjangoFilterBackend]
    filterset_class = AreaFilter

    def get_queryset(self) -> QuerySet[Area]:
        return Area.objects.annotate(
            children_count=Count("children"),
        ).order_by("name")

    @action(detail=True, methods=["get"])
    def rooms(self, request, pk=None):
        """Return public rooms in this area and all descendant areas."""
        from world.areas.services import get_rooms_in_area

        area = self.get_object()
        rooms = get_rooms_in_area(area)
        public_rooms = [r for r in rooms if r.is_public]
        serializer = AreaRoomSerializer(public_rooms, many=True)
        return Response(serializer.data)
```

**Step 4: Create urls**

```python
# src/world/areas/urls.py
from rest_framework.routers import DefaultRouter

from world.areas.views import AreaViewSet

router = DefaultRouter()
router.register("", AreaViewSet, basename="area")

app_name = "areas"
urlpatterns = router.urls
```

**Step 5: Register in web/urls.py**

Add: `path("api/areas/", include("world.areas.urls")),`

**Step 6: Run tests and lint**

Run: `echo "yes" | uv run arx test world.areas --keepdb`
Run: `ruff check src/world/areas/ --fix && ruff format src/world/areas/`

**Step 7: Commit**

```
feat(areas): add Area browsing API for location picker
```

---

### Task 3: Frontend — Types, queries, and URL helpers

**Files:**
- Create: `frontend/src/events/types.ts`
- Create: `frontend/src/events/queries.ts`
- Modify: `frontend/src/utils/urls.ts`

**Step 1: Create types**

```typescript
// frontend/src/events/types.ts
export type EventStatus = 'draft' | 'scheduled' | 'active' | 'completed' | 'cancelled';
export type TimePhase = 'dawn' | 'day' | 'dusk' | 'night';

export interface EventListItem {
  id: number;
  name: string;
  description: string;
  location: number;
  location_name: string;
  status: EventStatus;
  is_public: boolean;
  scheduled_real_time: string;
  scheduled_ic_time: string;
  time_phase: TimePhase;
  primary_host_name: string | null;
}

export interface EventHost {
  id: number;
  persona: number | null;
  persona_name: string | null;
  is_primary: boolean;
  added_at: string;
}

export interface EventInvitation {
  id: number;
  target_type: 'persona' | 'organization' | 'society';
  target_persona: number | null;
  target_organization: number | null;
  target_society: number | null;
  target_name: string | null;
  can_bring_guests: boolean;
  invited_at: string;
}

export interface EventModification {
  room_description_overlay: string;
}

export interface EventDetailData extends EventListItem {
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
  hosts: EventHost[];
  invitations: EventInvitation[];
  modification: EventModification | null;
}

export interface EventCreateData {
  name: string;
  description?: string;
  location: number;
  is_public: boolean;
  scheduled_real_time: string;
  scheduled_ic_time?: string;
  time_phase: TimePhase;
}

export interface PaginatedResponse<T> {
  count: number;
  page_size: number;
  num_pages: number;
  current_page: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

export interface AreaListItem {
  id: number;
  name: string;
  level: number;
  level_display: string;
  children_count: number;
}

export interface AreaRoom {
  id: number;
  name: string;
  area_name: string;
}
```

**Step 2: Create queries**

```typescript
// frontend/src/events/queries.ts
import { apiFetch } from '@/evennia_replacements/api';
import type {
  AreaListItem,
  AreaRoom,
  EventCreateData,
  EventDetailData,
  EventListItem,
  PaginatedResponse,
} from './types';

export async function fetchEvents(
  params: Record<string, string>
): Promise<PaginatedResponse<EventListItem>> {
  const query = new URLSearchParams(params).toString();
  const res = await apiFetch(`/api/events/?${query}`);
  if (!res.ok) throw new Error('Failed to load events');
  return res.json();
}

export async function fetchEvent(id: string): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/`);
  if (!res.ok) throw new Error('Failed to load event');
  return res.json();
}

export async function createEvent(data: EventCreateData): Promise<EventDetailData> {
  const res = await apiFetch('/api/events/', {
    method: 'POST',
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || err.non_field_errors?.[0] || 'Failed to create event');
  }
  return res.json();
}

export async function updateEvent(
  id: string,
  data: Partial<EventCreateData>
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/`, {
    method: 'PATCH',
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update event');
  return res.json();
}

export async function eventLifecycleAction(
  id: number,
  action: 'schedule' | 'start' | 'complete' | 'cancel'
): Promise<EventDetailData> {
  const res = await apiFetch(`/api/events/${id}/${action}/`, { method: 'POST' });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || `Failed to ${action} event`);
  }
  return res.json();
}

// Area browsing for location picker
export async function fetchAreas(parentId?: number): Promise<AreaListItem[]> {
  const params = parentId != null ? `?parent=${parentId}` : '?has_parent=false';
  const res = await apiFetch(`/api/areas/${params}`);
  if (!res.ok) throw new Error('Failed to load areas');
  return res.json();
}

export async function fetchAreaRooms(areaId: number): Promise<AreaRoom[]> {
  const res = await apiFetch(`/api/areas/${areaId}/rooms/`);
  if (!res.ok) throw new Error('Failed to load rooms');
  return res.json();
}
```

**Step 3: Update urls.ts**

Add to `ROUTES`:
```typescript
EVENTS: '/events',
```

Add to `urls`:
```typescript
// Event URLs
event: (id: number | string) => `${ROUTES.EVENTS}/${id}`,
eventCreate: () => `${ROUTES.EVENTS}/new`,
eventsList: () => ROUTES.EVENTS,
```

Add to `RouteParams`:
```typescript
eventId: string;
```

**Step 4: Commit**

```
feat(events-fe): add TypeScript types, API queries, and URL helpers
```

---

### Task 4: Frontend — Shared badge components

**Files:**
- Create: `frontend/src/events/components/EventStatusBadge.tsx`
- Create: `frontend/src/events/components/TimePhaseBadge.tsx`

**Step 1: Create EventStatusBadge**

```typescript
// frontend/src/events/components/EventStatusBadge.tsx
import { Badge } from '@/components/ui/badge';
import type { EventStatus } from '../types';

const STATUS_CONFIG: Record<EventStatus, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-gray-100 text-gray-700 border-gray-300' },
  scheduled: { label: 'Scheduled', className: 'bg-blue-100 text-blue-700 border-blue-300' },
  active: { label: 'Active', className: 'bg-green-100 text-green-700 border-green-300' },
  completed: { label: 'Completed', className: 'bg-muted text-muted-foreground' },
  cancelled: { label: 'Cancelled', className: 'bg-red-100 text-red-700 border-red-300' },
};

interface EventStatusBadgeProps {
  status: EventStatus;
}

export function EventStatusBadge({ status }: EventStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <Badge variant="outline" className={config.className}>
      {config.label}
    </Badge>
  );
}
```

**Step 2: Create TimePhaseBadge**

```typescript
// frontend/src/events/components/TimePhaseBadge.tsx
import { Moon, Sun, Sunrise, Sunset } from 'lucide-react';
import type { TimePhase } from '../types';

const PHASE_CONFIG: Record<TimePhase, { label: string; icon: typeof Sun; className: string }> = {
  dawn: { label: 'Dawn', icon: Sunrise, className: 'text-amber-500' },
  day: { label: 'Day', icon: Sun, className: 'text-yellow-500' },
  dusk: { label: 'Dusk', icon: Sunset, className: 'text-orange-500' },
  night: { label: 'Night', icon: Moon, className: 'text-indigo-400' },
};

interface TimePhaseBadgeProps {
  phase: TimePhase;
  showLabel?: boolean;
}

export function TimePhaseBadge({ phase, showLabel = false }: TimePhaseBadgeProps) {
  const config = PHASE_CONFIG[phase];
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1 ${config.className}`} title={config.label}>
      <Icon className="h-4 w-4" />
      {showLabel && <span className="text-xs">{config.label}</span>}
    </span>
  );
}
```

**Step 3: Commit**

```
feat(events-fe): add EventStatusBadge and TimePhaseBadge components
```

---

### Task 5: Frontend — EventCard component

**Files:**
- Create: `frontend/src/events/components/EventCard.tsx`

**Step 1: Create EventCard**

```typescript
// frontend/src/events/components/EventCard.tsx
import { Link } from 'react-router-dom';
import { Lock, MapPin, User } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { urls } from '@/utils/urls';
import { EventStatusBadge } from './EventStatusBadge';
import { TimePhaseBadge } from './TimePhaseBadge';
import type { EventListItem } from '../types';

interface EventCardProps {
  event: EventListItem;
  compact?: boolean;
}

export function EventCard({ event, compact = false }: EventCardProps) {
  const dateStr = new Date(event.scheduled_real_time).toLocaleDateString(undefined, {
    weekday: compact ? undefined : 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  const icDateStr = new Date(event.scheduled_ic_time).toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  const nameLink = compact ? (
    <a
      href={urls.event(event.id)}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium hover:underline"
    >
      {event.name}
    </a>
  ) : (
    <Link to={urls.event(event.id)} className="font-medium hover:underline">
      {event.name}
    </Link>
  );

  if (compact) {
    return (
      <div className="border-b px-3 py-2 last:border-b-0">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate">{nameLink}</div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{dateStr}</span>
              <TimePhaseBadge phase={event.time_phase} />
            </div>
          </div>
          <EventStatusBadge status={event.status} />
        </div>
        {event.primary_host_name && (
          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <User className="h-3 w-3" />
            <span>{event.primary_host_name}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {nameLink}
              {!event.is_public && <Lock className="h-3 w-3 text-muted-foreground" />}
            </div>
            {event.description && (
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">
                {event.description}
              </p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span title={`IC: ${icDateStr}`}>{dateStr}</span>
              <TimePhaseBadge phase={event.time_phase} showLabel />
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {event.location_name}
              </span>
              {event.primary_host_name && (
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {event.primary_host_name}
                </span>
              )}
            </div>
          </div>
          <EventStatusBadge status={event.status} />
        </div>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Commit**

```
feat(events-fe): add EventCard component with compact/full modes
```

---

### Task 6: Frontend — AreaDrilldownPicker

**Files:**
- Create: `frontend/src/events/components/AreaDrilldownPicker.tsx`

**Step 1: Create the area drill-down picker**

```typescript
// frontend/src/events/components/AreaDrilldownPicker.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight, Loader2, MapPin } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { fetchAreas, fetchAreaRooms } from '../queries';
import type { AreaListItem, AreaRoom } from '../types';

interface AreaDrilldownPickerProps {
  value: number | null;
  onChange: (roomProfileId: number, roomName: string) => void;
}

interface BreadcrumbItem {
  id: number;
  name: string;
}

export function AreaDrilldownPicker({ value, onChange }: AreaDrilldownPickerProps) {
  const [breadcrumbs, setBreadcrumbs] = useState<BreadcrumbItem[]>([]);
  const [selectedRoomName, setSelectedRoomName] = useState<string | null>(null);
  const currentParentId = breadcrumbs.length > 0 ? breadcrumbs[breadcrumbs.length - 1].id : undefined;

  const { data: areas = [], isLoading: areasLoading } = useQuery({
    queryKey: ['areas', currentParentId ?? 'root'],
    queryFn: () => fetchAreas(currentParentId),
  });

  const { data: rooms = [], isLoading: roomsLoading } = useQuery({
    queryKey: ['area-rooms', currentParentId],
    queryFn: () => fetchAreaRooms(currentParentId!),
    enabled: currentParentId != null && areas.length === 0,
  });

  const drillInto = (area: AreaListItem) => {
    setBreadcrumbs((prev) => [...prev, { id: area.id, name: area.name }]);
  };

  const navigateTo = (index: number) => {
    setBreadcrumbs((prev) => prev.slice(0, index + 1));
  };

  const goToRoot = () => {
    setBreadcrumbs([]);
  };

  const selectRoom = (room: AreaRoom) => {
    setSelectedRoomName(room.name);
    onChange(room.id, room.name);
  };

  if (value && selectedRoomName) {
    return (
      <div className="flex items-center gap-2 rounded-md border p-2">
        <MapPin className="h-4 w-4 text-muted-foreground" />
        <span className="flex-1 text-sm">{selectedRoomName}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => {
            setSelectedRoomName(null);
            onChange(null as unknown as number, '');
          }}
        >
          Change
        </Button>
      </div>
    );
  }

  const isLoading = areasLoading || roomsLoading;
  const showRooms = currentParentId != null && areas.length === 0;

  return (
    <div className="rounded-md border">
      {/* Breadcrumbs */}
      {breadcrumbs.length > 0 && (
        <div className="flex flex-wrap items-center gap-1 border-b px-3 py-2 text-sm">
          <button
            type="button"
            onClick={goToRoot}
            className="text-muted-foreground hover:text-foreground"
          >
            All
          </button>
          {breadcrumbs.map((crumb, idx) => (
            <span key={crumb.id} className="flex items-center gap-1">
              <ChevronRight className="h-3 w-3 text-muted-foreground" />
              <button
                type="button"
                onClick={() => navigateTo(idx)}
                className={
                  idx === breadcrumbs.length - 1
                    ? 'font-medium'
                    : 'text-muted-foreground hover:text-foreground'
                }
              >
                {crumb.name}
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Content */}
      <div className="max-h-64 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : showRooms ? (
          rooms.length === 0 ? (
            <p className="px-3 py-4 text-center text-sm text-muted-foreground">
              No public rooms in this area.
            </p>
          ) : (
            rooms.map((room) => (
              <button
                key={room.id}
                type="button"
                onClick={() => selectRoom(room)}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <MapPin className="h-4 w-4 text-muted-foreground" />
                <span>{room.name}</span>
              </button>
            ))
          )
        ) : areas.length === 0 ? (
          <p className="px-3 py-4 text-center text-sm text-muted-foreground">No areas found.</p>
        ) : (
          areas.map((area) => (
            <button
              key={area.id}
              type="button"
              onClick={() => drillInto(area)}
              className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <div>
                <span className="font-medium">{area.name}</span>
                <span className="ml-2 text-xs text-muted-foreground">{area.level_display}</span>
              </div>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                {area.children_count > 0 && <span>{area.children_count}</span>}
                <ChevronRight className="h-4 w-4" />
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```
feat(events-fe): add AreaDrilldownPicker for event location selection
```

---

### Task 7: Frontend — EventCreateForm and EventCreatePage

**Files:**
- Create: `frontend/src/events/components/EventCreateForm.tsx`
- Create: `frontend/src/events/pages/EventCreatePage.tsx`

**Step 1: Create EventCreateForm**

```typescript
// frontend/src/events/components/EventCreateForm.tsx
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
import { AreaDrilldownPicker } from './AreaDrilldownPicker';
import type { EventCreateData, TimePhase } from '../types';

const TIME_PHASES: { value: TimePhase; label: string }[] = [
  { value: 'dawn', label: 'Dawn' },
  { value: 'day', label: 'Day' },
  { value: 'dusk', label: 'Dusk' },
  { value: 'night', label: 'Night' },
];

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
        <AreaDrilldownPicker
          value={locationId}
          onChange={(id) => setLocationId(id)}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="event-time">Scheduled Time (OOC) *</Label>
        <Input
          id="event-time"
          type="datetime-local"
          value={scheduledRealTime}
          onChange={(e) => setScheduledRealTime(e.target.value)}
          min={new Date().toISOString().slice(0, 16)}
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
```

**Step 2: Create EventCreatePage**

```typescript
// frontend/src/events/pages/EventCreatePage.tsx
import { EventCreateForm } from '../components/EventCreateForm';

export function EventCreatePage() {
  return (
    <div className="container mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-6 text-2xl font-bold">Create Event</h1>
      <EventCreateForm />
    </div>
  );
}
```

**Step 3: Commit**

```
feat(events-fe): add EventCreateForm with area drill-down and EventCreatePage
```

---

### Task 8: Frontend — EventDetail component and EventDetailPage

**Files:**
- Create: `frontend/src/events/components/EventDetail.tsx`
- Create: `frontend/src/events/pages/EventDetailPage.tsx`

**Step 1: Create EventDetail**

```typescript
// frontend/src/events/components/EventDetail.tsx
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Lock, MapPin, User, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { EventStatusBadge } from './EventStatusBadge';
import { TimePhaseBadge } from './TimePhaseBadge';
import { eventLifecycleAction } from '../queries';
import type { EventDetailData } from '../types';

interface EventDetailProps {
  event: EventDetailData;
  isHost?: boolean;
  isStaff?: boolean;
}

export function EventDetail({ event, isHost = false, isStaff = false }: EventDetailProps) {
  const queryClient = useQueryClient();
  const canManage = isHost || isStaff;

  const lifecycleMutation = useMutation({
    mutationFn: (action: 'schedule' | 'start' | 'complete' | 'cancel') =>
      eventLifecycleAction(event.id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', String(event.id)] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const dateStr = new Date(event.scheduled_real_time).toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  const icDateStr = new Date(event.scheduled_ic_time).toLocaleString(undefined, {
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  });

  const primaryHost = event.hosts.find((h) => h.is_primary);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{event.name}</h1>
          <EventStatusBadge status={event.status} />
          {!event.is_public && <Lock className="h-4 w-4 text-muted-foreground" />}
        </div>
        {event.description && (
          <p className="mt-2 text-muted-foreground">{event.description}</p>
        )}
      </div>

      <Separator />

      {/* Info */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            <span>{event.location_name}</span>
          </div>
          <div className="text-sm">
            <div className="font-medium">{dateStr}</div>
            <div className="text-muted-foreground">IC: {icDateStr}</div>
          </div>
          <TimePhaseBadge phase={event.time_phase} showLabel />
        </div>

        <div className="space-y-3">
          <div className="text-sm">
            <span className="font-medium">
              {event.hosts.length === 1 ? 'Host' : 'Hosts'}:
            </span>
            <ul className="mt-1">
              {event.hosts.map((host) => (
                <li key={host.id} className="flex items-center gap-1">
                  <User className="h-3 w-3 text-muted-foreground" />
                  <span>
                    {host.persona_name || '(unknown)'}
                    {host.is_primary && (
                      <span className="ml-1 text-xs text-muted-foreground">(primary)</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Invitations - hosts/staff only */}
      {canManage && event.invitations.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4" />
              Invitations ({event.invitations.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {event.invitations.map((inv) => (
                <li key={inv.id} className="flex items-center gap-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs capitalize">
                    {inv.target_type}
                  </span>
                  <span>{inv.target_name || '(deleted)'}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Room modification */}
      {event.modification?.room_description_overlay && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Room Description Overlay</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm italic">{event.modification.room_description_overlay}</p>
          </CardContent>
        </Card>
      )}

      {/* Host actions */}
      {canManage && (
        <div className="flex flex-wrap gap-2">
          {event.status === 'draft' && (
            <Button
              onClick={() => lifecycleMutation.mutate('schedule')}
              disabled={lifecycleMutation.isPending}
            >
              Schedule
            </Button>
          )}
          {event.status === 'scheduled' && (
            <>
              <Button
                onClick={() => lifecycleMutation.mutate('start')}
                disabled={lifecycleMutation.isPending}
              >
                Start Event
              </Button>
              <Button
                variant="destructive"
                onClick={() => lifecycleMutation.mutate('cancel')}
                disabled={lifecycleMutation.isPending}
              >
                Cancel Event
              </Button>
            </>
          )}
          {event.status === 'active' && (
            <>
              <Button
                onClick={() => lifecycleMutation.mutate('complete')}
                disabled={lifecycleMutation.isPending}
              >
                Complete Event
              </Button>
              <Button
                variant="destructive"
                onClick={() => lifecycleMutation.mutate('cancel')}
                disabled={lifecycleMutation.isPending}
              >
                Cancel Event
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
```

**Step 2: Create EventDetailPage**

```typescript
// frontend/src/events/pages/EventDetailPage.tsx
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

  const { data: event, isLoading, error } = useQuery({
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

  // Determine if current user is a host (by checking if they have the account)
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
```

**Step 3: Commit**

```
feat(events-fe): add EventDetail component and EventDetailPage
```

---

### Task 9: Frontend — EventsListPage

**Files:**
- Create: `frontend/src/events/pages/EventsListPage.tsx`

**Step 1: Create EventsListPage**

```typescript
// frontend/src/events/pages/EventsListPage.tsx
import { useState } from 'react';
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

  // Debounce search
  const handleSearchChange = (value: string) => {
    setSearch(value);
    setPage(1);
    clearTimeout((window as any).__eventSearchTimeout);
    (window as any).__eventSearchTimeout = setTimeout(() => {
      setDebouncedSearch(value);
    }, 300);
  };

  const params: Record<string, string> = { status, page: String(page) };
  if (debouncedSearch) params.search = debouncedSearch;

  const { data, isLoading } = useQuery<PaginatedResponse<EventListItem>>({
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
        <Tabs value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
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
            onChange={(e) => handleSearchChange(e.target.value)}
            placeholder="Search events..."
            className="pl-9"
          />
        </div>
      </div>

      {isLoading ? (
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
```

**Step 2: Commit**

```
feat(events-fe): add EventsListPage with search, status tabs, pagination
```

---

### Task 10: Frontend — Routes, header navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Header.tsx`

**Step 1: Add routes to App.tsx**

Import the pages:
```typescript
import { EventsListPage } from '@/events/pages/EventsListPage';
import { EventDetailPage } from '@/events/pages/EventDetailPage';
import { EventCreatePage } from '@/events/pages/EventCreatePage';
```

Add routes (near the scenes routes):
```typescript
<Route path="/events" element={<EventsListPage />} />
<Route path="/events/new" element={<ProtectedRoute><EventCreatePage /></ProtectedRoute>} />
<Route path="/events/:id" element={<EventDetailPage />} />
```

**Step 2: Add to header navigation**

Add to the `links` array in `Header.tsx`:
```typescript
{ to: '/events', label: 'Events' },
```

Place it after Scenes (or wherever makes sense in the nav order).

**Step 3: Verify by running the dev server**

Run: `pnpm dev` (from `frontend/` directory) and check that `/events` loads.

**Step 4: Commit**

```
feat(events-fe): add routes and header navigation for events pages
```

---

### Task 11: Frontend — Game sidebar tab panel

**Files:**
- Create: `frontend/src/events/components/EventsSidebarPanel.tsx`
- Create: `frontend/src/game/components/SidebarTabPanel.tsx`
- Modify: `frontend/src/game/GamePage.tsx`

**Step 1: Create EventsSidebarPanel**

```typescript
// frontend/src/events/components/EventsSidebarPanel.tsx
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink, Loader2 } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { urls } from '@/utils/urls';
import { fetchEvents } from '../queries';
import { EventCard } from './EventCard';
import type { EventListItem, PaginatedResponse } from '../types';

const SIDEBAR_TABS = [
  { value: 'scheduled', label: 'Upcoming' },
  { value: 'active', label: 'Active' },
  { value: 'completed', label: 'Past' },
] as const;

export function EventsSidebarPanel() {
  const [status, setStatus] = useState('scheduled');

  const { data, isLoading } = useQuery<PaginatedResponse<EventListItem>>({
    queryKey: ['events', { status }],
    queryFn: () => fetchEvents({ status }),
  });

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-3 py-2">
        <Tabs value={status} onValueChange={setStatus}>
          <TabsList className="w-full">
            {SIDEBAR_TABS.map((tab) => (
              <TabsTrigger key={tab.value} value={tab.value} className="flex-1 text-xs">
                {tab.label}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
      </div>

      <div className="flex-1 overflow-y-auto">
        {isLoading ? (
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
```

**Step 2: Create SidebarTabPanel**

```typescript
// frontend/src/game/components/SidebarTabPanel.tsx
import { useState } from 'react';
import type { ReactNode } from 'react';
import { BookOpen, Calendar, MapPin } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface SidebarTabPanelProps {
  roomPanel: ReactNode;
  eventsPanel: ReactNode;
  codexPanel?: ReactNode;
}

export function SidebarTabPanel({ roomPanel, eventsPanel, codexPanel }: SidebarTabPanelProps) {
  return (
    <Tabs defaultValue="room" className="flex h-full flex-col">
      <TabsList className="mx-2 mt-2 grid w-auto grid-cols-3">
        <TabsTrigger value="room" className="gap-1 text-xs">
          <MapPin className="h-3 w-3" />
          Room
        </TabsTrigger>
        <TabsTrigger value="events" className="gap-1 text-xs">
          <Calendar className="h-3 w-3" />
          Events
        </TabsTrigger>
        <TabsTrigger value="codex" className="gap-1 text-xs">
          <BookOpen className="h-3 w-3" />
          Codex
        </TabsTrigger>
      </TabsList>
      <TabsContent value="room" className="mt-0 flex-1 overflow-y-auto">
        {roomPanel}
      </TabsContent>
      <TabsContent value="events" className="mt-0 flex-1 overflow-hidden">
        {eventsPanel}
      </TabsContent>
      <TabsContent value="codex" className="mt-0 flex-1 overflow-y-auto p-3">
        <p className="text-sm text-muted-foreground">Codex coming soon.</p>
      </TabsContent>
    </Tabs>
  );
}
```

**Step 3: Update GamePage.tsx**

Import `SidebarTabPanel` and `EventsSidebarPanel`, replace the `rightSidebar` prop:

```typescript
import { SidebarTabPanel } from './components/SidebarTabPanel';
import { EventsSidebarPanel } from '@/events/components/EventsSidebarPanel';

// In the JSX, replace rightSidebar prop:
rightSidebar={
  <SidebarTabPanel
    roomPanel={
      <RoomPanel
        character={active}
        room={activeSession?.room ?? null}
        scene={activeSession?.scene ?? null}
      />
    }
    eventsPanel={<EventsSidebarPanel />}
  />
}
```

**Step 4: Commit**

```
feat(events-fe): add EventsSidebarPanel and game sidebar tab panel
```

---

### Task 12: Lint, typecheck, and final verification

**Step 1: Run TypeScript type checking**

Run: `pnpm typecheck` (from `frontend/`)

**Step 2: Run ESLint**

Run: `pnpm lint` (from `frontend/`)

**Step 3: Fix any issues**

Run: `pnpm lint:fix` and `pnpm format`

**Step 4: Run backend tests**

Run: `echo "yes" | uv run arx test world.areas --keepdb`
Run: `echo "yes" | uv run arx test world.events --keepdb`

**Step 5: Commit any fixes**

```
style(events-fe): lint and typecheck fixes
```

---

### Task 13: Docs and roadmap

**Step 1: Commit design doc**

```
docs: add events frontend design and implementation plan
```
