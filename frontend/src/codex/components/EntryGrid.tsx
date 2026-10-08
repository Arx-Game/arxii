import { BookOpenCheck, Lock } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CodexEntryListItem } from '../types';
import '../codex.css';

interface EntryGridProps {
  entries: CodexEntryListItem[];
  /** Subject currently being browsed; used to gloss entries filed here from elsewhere. */
  subjectId?: number;
  /**
   * The account plays more than one character, so a per-character badge answers
   * "which of mine"; with one character the restricted tone already says it (#4191).
   */
  multiCharacter?: boolean;
  onSelectEntry: (entryId: number) => void;
}

export function EntryGrid({
  entries,
  subjectId,
  multiCharacter = false,
  onSelectEntry,
}: EntryGridProps) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
      {entries.map((entry) => (
        <EntryCard
          key={entry.id}
          entry={entry}
          subjectId={subjectId}
          multiCharacter={multiCharacter}
          onClick={() => onSelectEntry(entry.id)}
        />
      ))}
    </div>
  );
}

function EntryCard({
  entry,
  subjectId,
  multiCharacter,
  onClick,
}: {
  entry: CodexEntryListItem;
  subjectId?: number;
  multiCharacter: boolean;
  onClick: () => void;
}) {
  // A filing puts the entry in this listing without moving its canonical home
  // (see ADR-0275); gloss it here so the browser makes that clear.
  const filedFromElsewhere = subjectId !== undefined && entry.subject !== subjectId;

  return (
    <Card
      className={cn(
        'cursor-pointer transition-colors hover:bg-accent/50',
        !entry.is_public && 'codex-restricted'
      )}
      onClick={onClick}
    >
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
        {filedFromElsewhere && (
          <p className="text-xs text-muted-foreground">Filed from {entry.subject_name}</p>
        )}
      </CardHeader>
      <CardContent className="space-y-2">
        <p className="line-clamp-2 text-sm text-muted-foreground">{entry.summary}</p>
        {multiCharacter && entry.known_by.length > 0 && (
          <div className="flex flex-wrap items-center gap-1">
            {entry.known_by.map((knower) => (
              <Badge key={knower.roster_entry_id} variant="secondary" className="text-xs">
                {knower.status === 'known' ? (
                  <BookOpenCheck className="mr-1 h-3 w-3" />
                ) : (
                  <Lock className="mr-1 h-3 w-3" />
                )}
                {knower.character_name}
              </Badge>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
