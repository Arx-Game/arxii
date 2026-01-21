/**
 * Stage 5: Path Selection
 *
 * Character path (class) selection for CG.
 * Paths are the narrative-focused class system - they trace a character's
 * journey toward greatness through acts, legend, and achievements.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { motion } from 'framer-motion';
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
import { usePaths, useUpdateDraft } from '../queries';
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

export function PathStage({ draft }: PathStageProps) {
  const { data: paths, isLoading, error } = usePaths();
  const updateDraft = useUpdateDraft();

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
        <h2 className="text-2xl font-bold">Choose Your Path</h2>
        <p className="mt-2 text-muted-foreground">
          Your path defines your character's approach to the world - how they solve problems, face
          challenges, and pursue their goals. As you progress, your path will evolve and branch into
          more specialized directions.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {paths?.map((path) => {
          const isSelected = draft.selected_path?.id === path.id;
          const Icon = getPathIcon(path.icon_name);

          return (
            <Card
              key={path.id}
              className={cn(
                'relative cursor-pointer transition-all hover:shadow-md',
                isSelected && 'ring-2 ring-primary'
              )}
              onClick={() => handleSelectPath(path)}
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
                  <CardTitle className="text-lg">{path.name}</CardTitle>
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

      {paths?.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center text-muted-foreground">
          No paths are currently available for selection.
        </div>
      )}

      {draft.selected_path && (
        <Card className="border-primary/50 bg-primary/5">
          <CardHeader>
            <CardTitle className="text-lg">Selected: {draft.selected_path.name}</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{draft.selected_path.description}</p>
          </CardContent>
        </Card>
      )}
    </motion.div>
  );
}
