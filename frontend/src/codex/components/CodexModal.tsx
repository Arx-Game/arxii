import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ArrowRight, ExternalLink, Loader2 } from 'lucide-react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { useCodexEntry } from '../queries';
import { LoreSection, OOCSection } from './ContentSections';

interface CodexModalProps {
  entryId: number;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CodexModal({ entryId, open, onOpenChange }: CodexModalProps) {
  const [history, setHistory] = useState<number[]>([entryId]);
  const [historyIndex, setHistoryIndex] = useState(0);

  const currentEntryId = history[historyIndex];
  const { data: entry, isLoading, isError } = useCodexEntry(currentEntryId);

  const navigateToEntry = (id: number) => {
    const newHistory = history.slice(0, historyIndex + 1);
    newHistory.push(id);
    setHistory(newHistory);
    setHistoryIndex(newHistory.length - 1);
  };

  const goBack = () => {
    if (historyIndex > 0) setHistoryIndex(historyIndex - 1);
  };

  const goForward = () => {
    if (historyIndex < history.length - 1) setHistoryIndex(historyIndex + 1);
  };

  const canGoBack = historyIndex > 0;
  const canGoForward = historyIndex < history.length - 1;

  return (
    <Dialog
      open={open}
      onOpenChange={(open) => {
        if (!open) {
          // Reset history when modal closes
          setHistory([entryId]);
          setHistoryIndex(0);
        }
        onOpenChange(open);
      }}
    >
      <DialogContent className="sm:max-w-md">
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <Loader2 className="h-6 w-6 animate-spin" />
          </div>
        ) : isError ? (
          <div className="py-4 text-center text-muted-foreground">Unable to load entry</div>
        ) : entry ? (
          <>
            <DialogHeader>
              <div className="flex items-center justify-between">
                <DialogTitle>{entry.name}</DialogTitle>
                {(canGoBack || canGoForward) && (
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={goBack}
                      disabled={!canGoBack}
                      aria-label="Go back"
                    >
                      <ArrowLeft className="h-4 w-4" />
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      onClick={goForward}
                      disabled={!canGoForward}
                      aria-label="Go forward"
                    >
                      <ArrowRight className="h-4 w-4" />
                    </Button>
                  </div>
                )}
              </div>
            </DialogHeader>
            {entry.art_url && (
              <img
                src={entry.art_url}
                alt={entry.name}
                className="mb-2 h-40 w-full rounded-md object-cover"
              />
            )}
            <div className="space-y-3">
              <p className="text-sm text-muted-foreground">{entry.summary}</p>
              {entry.lore_content && (
                <LoreSection
                  content={entry.lore_content}
                  links={entry.lore_links}
                  onNavigate={navigateToEntry}
                />
              )}
              {entry.mechanics_content && (
                <OOCSection
                  content={entry.mechanics_content}
                  links={entry.mechanics_links}
                  onNavigate={navigateToEntry}
                />
              )}
              <Button asChild variant="outline" size="sm">
                <Link to={`/codex?entry=${entry.id}`} onClick={() => onOpenChange(false)}>
                  <ExternalLink className="mr-2 h-4 w-4" />
                  View in Codex
                </Link>
              </Button>
            </div>
          </>
        ) : (
          <div className="py-4 text-center text-muted-foreground">Entry not found</div>
        )}
      </DialogContent>
    </Dialog>
  );
}
