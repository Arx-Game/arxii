import { type ReactNode, useCallback, useState } from 'react';
import { Activity, Backpack, BookOpen, Calendar, MapPin, Scroll, Users } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface SidebarTabPanelProps {
  roomPanel: ReactNode;
  eventsPanel: ReactNode;
  /** #885 story tray — the player's active missions, live where they stand. */
  storiesPanel?: ReactNode;
  codexPanel?: ReactNode;
  /** #1463 presence tab — who's online + where (coloured area paths). */
  presencePanel?: ReactNode;
  /** #1446 qualitative status tab — health/fatigue/anima as words, coin + AP as numbers. */
  statusPanel?: ReactNode;
  /** #1446 read-only carried-items tab — the sheet describes; the scene does. */
  inventoryPanel?: ReactNode;
  /**
   * Label for the room tab. Defaults to ``"Room"`` but the parent can
   * pass the currently-focused subject (a character or item name) so the
   * tab reflects what the right sidebar is actually showing. Long names
   * are visually truncated; the full label remains accessible via the
   * tab's ``title`` tooltip.
   */
  roomTabLabel?: string;
}

export function SidebarTabPanel({
  roomPanel,
  eventsPanel,
  storiesPanel,
  codexPanel,
  presencePanel,
  statusPanel,
  inventoryPanel,
  roomTabLabel,
}: SidebarTabPanelProps) {
  const [activeTab, setActiveTab] = useState('room');
  const [activatedTabs, setActivatedTabs] = useState<Set<string>>(new Set(['room']));

  const handleTabChange = useCallback((value: string) => {
    setActiveTab(value);
    setActivatedTabs((prev) => {
      if (prev.has(value)) return prev;
      const next = new Set(prev);
      next.add(value);
      return next;
    });
  }, []);

  const label = roomTabLabel ?? 'Room';

  return (
    <Tabs value={activeTab} onValueChange={handleTabChange} className="flex h-full flex-col">
      <TabsList className="mx-2 mt-2 grid w-auto grid-cols-7">
        <TabsTrigger value="room" className="gap-1 text-xs" title={label}>
          <MapPin className="h-3 w-3 shrink-0" />
          <span className="inline-block max-w-[8rem] truncate">{label}</span>
        </TabsTrigger>
        <TabsTrigger value="who" className="gap-1 text-xs">
          <Users className="h-3 w-3" />
          Who
        </TabsTrigger>
        <TabsTrigger value="stories" className="gap-1 text-xs">
          <Scroll className="h-3 w-3" />
          Stories
        </TabsTrigger>
        <TabsTrigger value="events" className="gap-1 text-xs">
          <Calendar className="h-3 w-3" />
          Events
        </TabsTrigger>
        <TabsTrigger value="codex" className="gap-1 text-xs">
          <BookOpen className="h-3 w-3" />
          Codex
        </TabsTrigger>
        <TabsTrigger value="status" className="gap-1 text-xs">
          <Activity className="h-3 w-3" />
          Status
        </TabsTrigger>
        <TabsTrigger value="inventory" className="gap-1 text-xs">
          <Backpack className="h-3 w-3" />
          Items
        </TabsTrigger>
      </TabsList>
      <TabsContent value="room" className="mt-0 flex-1 overflow-y-auto">
        {roomPanel}
      </TabsContent>
      <TabsContent value="who" className="mt-0 flex-1 overflow-y-auto">
        {activatedTabs.has('who')
          ? (presencePanel ?? (
              <p className="p-3 text-sm text-muted-foreground">No presence to show.</p>
            ))
          : null}
      </TabsContent>
      <TabsContent value="stories" className="mt-0 flex-1 overflow-y-auto">
        {activatedTabs.has('stories')
          ? (storiesPanel ?? (
              <p className="p-3 text-sm text-muted-foreground">No stories to show.</p>
            ))
          : null}
      </TabsContent>
      <TabsContent value="events" className="mt-0 flex-1 overflow-hidden">
        {activatedTabs.has('events') ? eventsPanel : null}
      </TabsContent>
      <TabsContent value="codex" className="mt-0 flex-1 overflow-y-auto p-3">
        {activatedTabs.has('codex')
          ? (codexPanel ?? <p className="text-sm text-muted-foreground">Codex coming soon.</p>)
          : null}
      </TabsContent>
      <TabsContent value="status" className="mt-0 flex-1 overflow-y-auto p-3">
        {activatedTabs.has('status')
          ? (statusPanel ?? <p className="text-sm text-muted-foreground">No status to show.</p>)
          : null}
      </TabsContent>
      <TabsContent value="inventory" className="mt-0 flex-1 overflow-y-auto p-3">
        {activatedTabs.has('inventory')
          ? (inventoryPanel ?? <p className="text-sm text-muted-foreground">Nothing carried.</p>)
          : null}
      </TabsContent>
    </Tabs>
  );
}
