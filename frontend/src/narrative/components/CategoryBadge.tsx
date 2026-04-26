/**
 * Category badge for narrative message categories.
 * Color-coded by category type.
 */

import { Badge } from '@/components/ui/badge';
import type { NarrativeCategory } from '../types';

const CATEGORY_LABELS: Record<NarrativeCategory, string> = {
  story: 'Story',
  atmosphere: 'Atmosphere',
  visions: 'Visions',
  happenstance: 'Happenstance',
  system: 'System',
};

const CATEGORY_CLASSES: Record<NarrativeCategory, string> = {
  story: 'bg-blue-600 text-white border-transparent',
  atmosphere: 'bg-purple-600 text-white border-transparent',
  visions: 'bg-pink-600 text-white border-transparent',
  happenstance: 'bg-amber-600 text-white border-transparent',
  system: 'bg-gray-500 text-white border-transparent',
};

interface CategoryBadgeProps {
  category: NarrativeCategory;
}

export function CategoryBadge({ category }: CategoryBadgeProps) {
  return <Badge className={CATEGORY_CLASSES[category]}>{CATEGORY_LABELS[category]}</Badge>;
}
