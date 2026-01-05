/**
 * Placeholder stage component for stages that depend on systems not yet implemented.
 * These will be expanded as the underlying systems are built.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Switch } from '@/components/ui/switch';
import { motion } from 'framer-motion';
import { Construction } from 'lucide-react';
import { useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';

interface PlaceholderStageProps {
  draft: CharacterDraft;
  title: string;
  description: string;
  completionKey: string;
}

export function PlaceholderStage({
  draft,
  title,
  description,
  completionKey,
}: PlaceholderStageProps) {
  const updateDraft = useUpdateDraft();
  const isComplete = draft.draft_data[completionKey] as boolean | undefined;

  const handleToggle = (checked: boolean) => {
    updateDraft.mutate({
      draft_data: {
        ...draft.draft_data,
        [completionKey]: checked,
      },
    });
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="space-y-8"
    >
      <div>
        <h2 className="text-2xl font-bold">{title}</h2>
        <p className="mt-2 text-muted-foreground">{description}</p>
      </div>

      <Card className="max-w-lg border-dashed">
        <CardHeader>
          <div className="flex items-center gap-2">
            <Construction className="h-5 w-5 text-amber-500" />
            <CardTitle className="text-base">Coming Soon</CardTitle>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <CardDescription>
            This section is under development. For now, you can mark it as complete to continue with
            character creation.
          </CardDescription>
          <div className="flex items-center gap-2">
            <Switch
              id={`${completionKey}-toggle`}
              checked={isComplete ?? false}
              onCheckedChange={handleToggle}
            />
            <label htmlFor={`${completionKey}-toggle`} className="cursor-pointer text-sm">
              Mark as complete (placeholder)
            </label>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
}

// Specific stage wrappers

export function AttributesStage({ draft }: { draft: CharacterDraft }) {
  return (
    <PlaceholderStage
      draft={draft}
      title="Attributes"
      description="Allocate your character's primary statistics."
      completionKey="attributes_complete"
    />
  );
}

export function PathSkillsStage({ draft }: { draft: CharacterDraft }) {
  return (
    <PlaceholderStage
      draft={draft}
      title="Path & Skills"
      description="Choose your character's path (class) and starting skills."
      completionKey="path_skills_complete"
    />
  );
}

export function TraitsStage({ draft }: { draft: CharacterDraft }) {
  return (
    <PlaceholderStage
      draft={draft}
      title="Traits"
      description="Select advantages and disadvantages that shape your character's life."
      completionKey="traits_complete"
    />
  );
}
