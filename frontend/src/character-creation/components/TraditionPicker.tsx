/**
 * TraditionPicker — tradition selection card grid for character creation.
 *
 * Displays available magical traditions for the character's beginning,
 * with selection handling and optional CodexModal for lore viewing.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CodexModal } from '@/codex/components/CodexModal';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { CheckCircle2, LinkIcon, Loader2, ScrollText } from 'lucide-react';
import { useState } from 'react';
import { useSelectTradition, useTraditions } from '../queries';
import type { CharacterDraft } from '../types';

interface TraditionPickerProps {
  draft: CharacterDraft;
  beginningId: number;
}

export function TraditionPicker({ draft, beginningId }: TraditionPickerProps) {
  const { data: traditions, isLoading, error } = useTraditions(beginningId);
  const selectTradition = useSelectTradition();

  const [codexEntryId, setCodexEntryId] = useState<number | null>(null);
  const [codexOpen, setCodexOpen] = useState(false);

  const handleSelect = (traditionId: number) => {
    const isAlreadySelected = draft.selected_tradition?.id === traditionId;
    selectTradition.mutate({
      draftId: draft.id,
      traditionId: isAlreadySelected ? null : traditionId,
    });
  };

  const handleViewLore = (e: React.MouseEvent, entryId: number) => {
    e.stopPropagation();
    setCodexEntryId(entryId);
    setCodexOpen(true);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading traditions...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
        Failed to load traditions. Please try again.
      </div>
    );
  }

  if (!traditions || traditions.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-xl font-semibold">Choose Your Tradition</h3>
        <p className="mt-1 text-muted-foreground">
          Your tradition reflects how your character learned and practices magic. It shapes the
          techniques and gifts available to you.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {traditions.map((tradition, index) => {
          const isSelected = draft.selected_tradition?.id === tradition.id;
          const hasCodex = tradition.codex_entry_ids.length > 0;

          return (
            <motion.div
              key={tradition.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.2, delay: index * 0.05 }}
            >
              <Card
                className={cn(
                  'relative cursor-pointer transition-all hover:shadow-md',
                  isSelected && 'ring-2 ring-primary'
                )}
                onClick={() => handleSelect(tradition.id)}
              >
                {isSelected && (
                  <div className="absolute right-2 top-2">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                  </div>
                )}
                <CardHeader className="pb-2">
                  <CardTitle className="text-lg">{tradition.name}</CardTitle>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">
                    {tradition.description}
                  </CardDescription>
                  {tradition.required_distinction_id && (
                    <Badge variant="outline" className="mt-2 gap-1 text-xs">
                      <LinkIcon className="h-3 w-3" />
                      Includes required distinction
                    </Badge>
                  )}
                  {hasCodex && (
                    <Button
                      variant="ghost"
                      size="sm"
                      className="mt-3 gap-2 text-muted-foreground hover:text-foreground"
                      onClick={(e) => handleViewLore(e, tradition.codex_entry_ids[0])}
                    >
                      <ScrollText className="h-4 w-4" />
                      View Lore
                    </Button>
                  )}
                </CardContent>
              </Card>
            </motion.div>
          );
        })}
      </div>

      {codexEntryId !== null && (
        <CodexModal entryId={codexEntryId} open={codexOpen} onOpenChange={setCodexOpen} />
      )}
    </div>
  );
}
