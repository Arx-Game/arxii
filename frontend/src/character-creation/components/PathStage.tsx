/**
 * Stage 5: Path Selection
 *
 * Character path (class) selection for CG.
 * Paths are the narrative-focused class system - they trace a character's
 * journey toward greatness through acts, legend, and achievements.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { cn } from '@/lib/utils';
import { AnimatePresence, motion } from 'framer-motion';
import {
  BookOpen,
  CheckCircle2,
  Crown,
  Eye,
  Flame,
  Heart,
  type LucideIcon,
  Loader2,
  MessageCircle,
  Moon,
  Shield,
  Sparkles,
  Sun,
  Swords,
  TreePine,
  Wand2,
  Zap,
} from 'lucide-react';
import { useState } from 'react';
import { useCGExplanations, usePaths, useUpdateDraft } from '../queries';
import type { CharacterDraft, Path } from '../types';

interface PathStageProps {
  draft: CharacterDraft;
}

// Map icon_name strings (from Django admin) to Lucide components
// Staff can use these names in the Path.icon_name field
const ICON_MAP: Record<string, LucideIcon> = {
  swords: Swords,
  eye: Eye,
  'message-circle': MessageCircle,
  'book-open': BookOpen,
  sparkles: Sparkles,
  shield: Shield,
  crown: Crown,
  flame: Flame,
  heart: Heart,
  moon: Moon,
  sun: Sun,
  'tree-pine': TreePine,
  wand2: Wand2,
  zap: Zap,
};

/** Get icon component from icon_name, with fallback to Sparkles */
function getPathIcon(iconName: string | undefined): LucideIcon {
  if (!iconName) return Sparkles;
  return ICON_MAP[iconName.toLowerCase()] || Sparkles;
}

/** Sticky sidebar showing full path details on hover */
function PathDetailPanel({ path }: { path: Path | null }) {
  if (!path) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Hover over a path to see its full description.
        </CardContent>
      </Card>
    );
  }

  const Icon = getPathIcon(path.icon_name);

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={path.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
      >
        <Card>
          <CardHeader>
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary/20 text-primary">
                <Icon className="h-5 w-5" />
              </div>
              <CardTitle className="text-lg">
                {path.codex_entry_ids?.length > 0 ? (
                  <CodexTerm entryId={path.codex_entry_ids[0]}>{path.name}</CodexTerm>
                ) : (
                  path.name
                )}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="whitespace-pre-wrap leading-relaxed text-muted-foreground">
              {path.description}
            </p>
            {path.aspects.length > 0 && (
              <div>
                <div className="mb-2 text-sm font-medium">Aspects</div>
                <div className="flex flex-wrap gap-1">
                  {path.aspects.map((aspect) => (
                    <span
                      key={aspect}
                      className="rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary"
                    >
                      {aspect}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

export function PathStage({ draft }: PathStageProps) {
  const { data: paths, isLoading, error } = usePaths();
  const { data: copy } = useCGExplanations();
  const updateDraft = useUpdateDraft();
  const [hoveredPath, setHoveredPath] = useState<Path | null>(null);

  const handleSelectPath = (path: Path) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_path_id: path.id,
      },
    });
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive">
        Failed to load paths. Please try again.
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="theme-heading text-2xl font-bold">{copy?.path_heading ?? ''}</h2>
        <p className="mt-2 text-muted-foreground">{copy?.path_intro ?? ''}</p>
        {copy?.path_lore_durance && (
          <p className="mt-2 text-sm text-muted-foreground">{copy.path_lore_durance}</p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[1fr_300px]">
        {/* Path cards */}
        <div className="grid gap-4 sm:grid-cols-2">
          {paths?.map((path) => {
            const isSelected = draft.selected_path?.id === path.id;
            const Icon = getPathIcon(path.icon_name);

            return (
              <Card
                key={path.id}
                className={cn(
                  'relative cursor-pointer transition-all hover:shadow-md',
                  isSelected && 'ring-2 ring-primary',
                  hoveredPath?.id === path.id && !isSelected && 'ring-1 ring-primary/30'
                )}
                onClick={() => handleSelectPath(path)}
                onMouseEnter={() => setHoveredPath(path)}
                onMouseLeave={() => setHoveredPath(null)}
              >
                {isSelected && (
                  <div className="absolute right-2 top-2">
                    <CheckCircle2 className="h-5 w-5 text-primary" />
                  </div>
                )}
                <CardHeader className="pb-2">
                  <div className="flex items-center gap-3">
                    <div
                      className={cn(
                        'flex h-10 w-10 items-center justify-center rounded-lg',
                        isSelected ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
                      )}
                    >
                      <Icon className="h-5 w-5" />
                    </div>
                    <CardTitle className="text-lg">
                      {path.codex_entry_ids?.length > 0 ? (
                        <CodexTerm entryId={path.codex_entry_ids[0]}>{path.name}</CodexTerm>
                      ) : (
                        path.name
                      )}
                    </CardTitle>
                  </div>
                </CardHeader>
                <CardContent>
                  <CardDescription className="line-clamp-3">{path.description}</CardDescription>
                  {path.aspects.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-1">
                      {path.aspects.map((aspect) => (
                        <span
                          key={aspect}
                          className="rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground"
                        >
                          {aspect}
                        </span>
                      ))}
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>

        {/* Sidebar: Path detail panel (desktop only) */}
        <div className="hidden lg:block">
          <div className="sticky top-4">
            <PathDetailPanel path={hoveredPath ?? draft.selected_path ?? null} />
          </div>
        </div>
      </div>

      {/* Mobile: Path detail below cards */}
      {draft.selected_path && (
        <div className="lg:hidden">
          <PathDetailPanel path={draft.selected_path} />
        </div>
      )}

      {paths?.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No paths are currently available for selection.
        </div>
      )}
    </motion.div>
  );
}
