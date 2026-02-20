/**
 * TraditionPicker — tradition selection card grid for character creation.
 *
 * Displays available magical traditions for the character's beginning,
 * with selection handling and a hover-triggered side panel for full
 * descriptions and codex lore links.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
import { CheckCircle2, LinkIcon, Loader2, Sparkles } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useSelectTradition, useTraditions } from '../queries';
import type { CharacterDraft } from '../types';

interface TraditionCardTradition {
  id: number;
  name: string;
  description: string;
  required_distinction_id: number | null;
  codex_entry_ids: number[];
}

interface TraditionCardProps {
  tradition: TraditionCardTradition;
  isSelected: boolean;
  isBeingSelected: boolean;
  index: number;
  onSelect: (traditionId: number) => void;
  onHover: (tradition: TraditionCardTradition | null) => void;
}

function TraditionCard({
  tradition,
  isSelected,
  isBeingSelected,
  index,
  onSelect,
  onHover,
}: TraditionCardProps) {
  const [showGlow, setShowGlow] = useState(false);
  const prevSelected = useRef(isSelected);

  useEffect(() => {
    if (isSelected && !prevSelected.current) {
      setShowGlow(true);
      const timer = setTimeout(() => setShowGlow(false), 600);
      return () => clearTimeout(timer);
    }
    prevSelected.current = isSelected;
  }, [isSelected]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2, delay: index * 0.05 }}
    >
      <Card
        className={cn(
          'relative cursor-pointer transition-all hover:shadow-md',
          isSelected && 'ring-2 ring-primary',
          showGlow && 'animate-selection-glow'
        )}
        onClick={() => onSelect(tradition.id)}
        onMouseEnter={() => onHover(tradition)}
        onMouseLeave={() => onHover(null)}
      >
        {isBeingSelected ? (
          <div className="absolute right-2 top-2">
            <Loader2 className="h-5 w-5 animate-spin text-primary" />
          </div>
        ) : (
          isSelected && (
            <div className="absolute right-2 top-2">
              <CheckCircle2 className="h-5 w-5 text-primary" />
            </div>
          )
        )}
        <CardHeader className="pb-2">
          <CardTitle className="text-lg">{tradition.name}</CardTitle>
        </CardHeader>
        <CardContent>
          <CardDescription className="line-clamp-3">{tradition.description}</CardDescription>
          {tradition.required_distinction_id && (
            <Badge variant="outline" className="mt-2 gap-1 text-xs">
              <LinkIcon className="h-3 w-3" />
              Includes required distinction
            </Badge>
          )}
        </CardContent>
      </Card>
    </motion.div>
  );
}

interface TraditionPickerProps {
  draft: CharacterDraft;
  beginningId: number;
}

export function TraditionPicker({ draft, beginningId }: TraditionPickerProps) {
  const { data: traditions, isLoading, error } = useTraditions(beginningId);
  const selectTradition = useSelectTradition();
  const [hoveredTradition, setHoveredTradition] = useState<TraditionCardTradition | null>(null);

  const isMutating = selectTradition.isPending;
  const mutatingTraditionId = selectTradition.variables?.traditionId;

  const handleSelect = (traditionId: number) => {
    if (isMutating) return;
    const isAlreadySelected = draft.selected_tradition?.id === traditionId;
    selectTradition.mutate({
      draftId: draft.id,
      traditionId: isAlreadySelected ? null : traditionId,
    });
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
    return (
      <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-muted-foreground/25 p-8 text-center">
        <Sparkles className="mb-2 h-8 w-8 text-muted-foreground/50" />
        <p className="text-sm text-muted-foreground">
          No traditions are available for this beginning.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="theme-heading text-xl font-semibold">Choose Your Tradition</h3>
        <p className="mt-1 text-muted-foreground">
          Your tradition reflects how your character learned and practices magic. It shapes the
          techniques and gifts available to you.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Card Grid */}
        <div
          className={cn(
            'grid gap-4 sm:grid-cols-2',
            isMutating && 'pointer-events-none opacity-60'
          )}
        >
          {traditions.map((tradition, index) => (
            <TraditionCard
              key={tradition.id}
              tradition={tradition}
              isSelected={draft.selected_tradition?.id === tradition.id}
              isBeingSelected={isMutating && mutatingTraditionId === tradition.id}
              index={index}
              onSelect={handleSelect}
              onHover={setHoveredTradition}
            />
          ))}
        </div>

        {/* Sidebar: Hover Detail Panel */}
        <div className="hidden lg:block">
          <div className="sticky top-4">
            {hoveredTradition ? (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="text-sm font-medium">
                    {hoveredTradition.codex_entry_ids.length > 0 ? (
                      <CodexTerm entryId={hoveredTradition.codex_entry_ids[0]}>
                        {hoveredTradition.name}
                      </CodexTerm>
                    ) : (
                      hoveredTradition.name
                    )}
                  </CardTitle>
                </CardHeader>
                <CardContent className="space-y-3 pt-0">
                  <p className="text-xs text-muted-foreground">{hoveredTradition.description}</p>
                  {hoveredTradition.required_distinction_id && (
                    <Badge variant="outline" className="gap-1 text-xs">
                      <LinkIcon className="h-3 w-3" />
                      Includes required distinction
                    </Badge>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card className="border-dashed">
                <CardContent className="flex items-center justify-center py-8">
                  <p className="text-center text-xs text-muted-foreground">
                    Hover over a tradition to see its full description.
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
