import { BookOpenCheck, Lock } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Breadcrumb } from './Breadcrumb';
import { LoreSection, OOCSection } from './ContentSections';
import type { CodexEntryDetail as CodexEntryDetailType } from '../types';

interface EntryDetailProps {
  entry: CodexEntryDetailType;
  onNavigateBreadcrumb: (type: 'home' | 'category' | 'subject', id?: number) => void;
}

export function EntryDetail({ entry, onNavigateBreadcrumb }: EntryDetailProps) {
  const isUncovered = entry.knowledge_status === 'uncovered';
  const navigate = useNavigate();

  // On the full page, inline links use React Router navigation so browser
  // back/forward works natively.
  const handleNavigate = (entryId: number) => {
    navigate(`/codex?entry=${entryId}`);
  };

  const breadcrumbItems = entry.subject_path.map((segment) => ({
    label: segment.name,
    onClick: () => onNavigateBreadcrumb(segment.type, segment.id),
  }));

  return (
    <Card>
      <CardHeader>
        <Breadcrumb items={breadcrumbItems} />
        <div className="flex items-center gap-2">
          <CardTitle>{entry.name}</CardTitle>
          {isUncovered && (
            <Badge variant="outline">
              <Lock className="mr-1 h-3 w-3" />
              Researching
            </Badge>
          )}
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        {entry.known_by.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-sm text-muted-foreground">Known by:</span>
            {entry.known_by.map((knower) => (
              <Badge key={knower.roster_entry_id} variant="secondary">
                {knower.status === 'known' ? (
                  <BookOpenCheck className="mr-1 h-3 w-3" />
                ) : (
                  <Lock className="mr-1 h-3 w-3" />
                )}
                {knower.character_name}
                {knower.status === 'uncovered' && entry.learn_threshold ? (
                  <span className="ml-1 text-muted-foreground">
                    {knower.research_progress}/{entry.learn_threshold}
                  </span>
                ) : null}
              </Badge>
            ))}
          </div>
        )}
        {isUncovered && entry.research_progress !== null && (entry.learn_threshold ?? 0) > 0 && (
          <div className="rounded-lg bg-muted p-3">
            <div className="mb-1 text-sm font-medium">Research Progress</div>
            <div className="flex items-center gap-2">
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-background">
                <div
                  className="h-full bg-primary"
                  style={{
                    width: `${Math.min(100, (entry.research_progress / entry.learn_threshold) * 100)}%`,
                  }}
                />
              </div>
              <span className="text-sm text-muted-foreground">
                {entry.research_progress}/{entry.learn_threshold}
              </span>
            </div>
          </div>
        )}
        {entry.perspective_of && (
          <p className="text-sm italic text-muted-foreground">As told by {entry.perspective_of}</p>
        )}
        {entry.lore_content || entry.mechanics_content ? (
          <div className="space-y-3">
            {entry.lore_content && (
              <LoreSection
                content={entry.lore_content}
                links={entry.lore_links}
                onNavigate={handleNavigate}
              />
            )}
            {entry.mechanics_content && (
              <OOCSection
                content={entry.mechanics_content}
                links={entry.mechanics_links}
                onNavigate={handleNavigate}
              />
            )}
          </div>
        ) : (
          <div className="italic text-muted-foreground">
            {entry.summary}
            <p className="mt-2 text-sm">Continue researching to uncover the full content.</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
