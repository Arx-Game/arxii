import type { LucideIcon } from 'lucide-react';
import { Eye, Hand, MessageCircle } from 'lucide-react';

// Lookup mapping action strings to icon components
export const ACTION_ICON_MAP: Record<string, LucideIcon> = {
  look: Eye,
  get: Hand,
  talk: MessageCircle,
};
