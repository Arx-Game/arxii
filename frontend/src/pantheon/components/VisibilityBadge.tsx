/**
 * The Codex tier a god sits at (#3780): Public, Obscure (with the organization that knows
 * it), or Secret. Read through the linked entry, never a field on the being.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { Visibility } from '../types';
import { VISIBILITY_LABELS } from '../visibility';

const CLASSES: Record<Visibility, string> = {
  public: 'border-green-300 bg-green-50 text-green-800 dark:bg-green-950/40 dark:text-green-300',
  obscure: 'border-amber-300 bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300',
  secret: 'border-zinc-300 bg-zinc-50 text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300',
};

interface VisibilityBadgeProps {
  visibility: Visibility;
  organizationName?: string;
}

export function VisibilityBadge({ visibility, organizationName }: VisibilityBadgeProps) {
  return (
    <Badge variant="outline" className={cn('font-medium', CLASSES[visibility])}>
      {VISIBILITY_LABELS[visibility]}
      {visibility === 'obscure' && organizationName ? ` · ${organizationName}` : ''}
    </Badge>
  );
}
