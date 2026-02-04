import { Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { CodexEntryListItem } from '../types';

interface EntryGridProps {
  entries: CodexEntryListItem[];
  onSelectEntry: (entryId: number) => void;
}

export function EntryGrid({ entries, onSelectEntry }: EntryGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {entries.map((entry) => (
        <EntryCard key={entry.id} entry={entry} onClick={() => onSelectEntry(entry.id)} />
      ))}
    </div>
  );
}

function EntryCard({ entry, onClick }: { entry: CodexEntryListItem; onClick: () => void }) {
  return (
    <Card className="cursor-pointer transition-colors hover:bg-accent/50" onClick={onClick}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <CardTitle className="text-base">{entry.name}</CardTitle>
          {entry.knowledge_status === 'uncovered' && (
            <Badge variant="outline" className="text-xs">
              <Lock className="mr-1 h-3 w-3" />
              Researching
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        <p className="line-clamp-2 text-sm text-muted-foreground">{entry.summary}</p>
      </CardContent>
    </Card>
  );
}
