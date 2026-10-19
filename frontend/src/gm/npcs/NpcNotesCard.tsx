import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import type { MyRosterEntry } from '@/roster/types';

/** The GM's notes for whoever plays this NPC; renders nothing when there are none. */
export function NpcNotesCard({ entry }: { entry: Pick<MyRosterEntry, 'name' | 'npc_notes'> }) {
  if (!entry.npc_notes) return null;
  const paragraphs = entry.npc_notes.split(/\n{2,}/).filter((p) => p.trim());
  return (
    <Card data-testid="npc-notes-card">
      <CardHeader className="pb-2">
        <CardTitle className="font-display text-base">
          Notes for whoever plays {entry.name}
        </CardTitle>
      </CardHeader>
      <CardContent className="max-h-64 space-y-2 overflow-y-auto text-sm">
        {paragraphs.map((p, i) => (
          <p key={i} className="whitespace-pre-wrap">
            {p}
          </p>
        ))}
      </CardContent>
    </Card>
  );
}
