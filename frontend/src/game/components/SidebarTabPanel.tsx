import { type ReactNode, useCallback, useState } from 'react';
import { BookOpen, Calendar, MapPin } from 'lucide-react';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface SidebarTabPanelProps {
  roomPanel: ReactNode;
  eventsPanel: ReactNode;
  codexPanel?: ReactNode;
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
  codexPanel,
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
      <TabsList className="mx-2 mt-2 grid w-auto grid-cols-3">
        <TabsTrigger value="room" className="gap-1 text-xs" title={label}>
          <MapPin className="h-3 w-3 shrink-0" />
          <span className="inline-block max-w-[8rem] truncate">{label}</span>
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
        {activatedTabs.has('events') ? eventsPanel : null}
      </TabsContent>
      <TabsContent value="codex" className="mt-0 flex-1 overflow-y-auto p-3">
        {activatedTabs.has('codex')
          ? (codexPanel ?? <p className="text-sm text-muted-foreground">Codex coming soon.</p>)
          : null}
      </TabsContent>
    </Tabs>
  );
}
