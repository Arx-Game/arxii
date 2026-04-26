/**
 * Scope badge for story scope values (CHARACTER / GROUP / GLOBAL).
 * Matches the player-facing copy from the plan.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { StoryScope } from '../types';

const SCOPE_LABELS: Record<StoryScope, string> = {
  character: 'Personal',
  group: 'Group',
  global: 'Global',
};

const SCOPE_CLASSES: Record<StoryScope, string> = {
  character: 'bg-indigo-600 text-white border-transparent',
  group: 'bg-teal-600 text-white border-transparent',
  global: 'bg-orange-600 text-white border-transparent',
};

interface ScopeBadgeProps {
  scope: StoryScope;
  className?: string;
}

export function ScopeBadge({ scope, className }: ScopeBadgeProps) {
  return <Badge className={cn(SCOPE_CLASSES[scope], className)}>{SCOPE_LABELS[scope]}</Badge>;
}
