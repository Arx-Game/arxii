/**
 * Starting Area Card component
 *
 * Displays a selectable starting area with crest image (or gradient placeholder),
 * name, and hover description.
 */

import { Card, CardContent } from '@/components/ui/card';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { cn } from '@/lib/utils';
import { CheckCircle2, Lock } from 'lucide-react';
import type { StartingArea } from '../types';

interface StartingAreaCardProps {
  area: StartingArea;
  isSelected: boolean;
  onSelect: (area: StartingArea) => void;
}

/**
 * Generate a gradient background color based on the area name.
 * Creates a consistent but varied appearance for each area.
 */
function getGradientColors(name: string): [string, string] {
  // Simple hash function for consistent colors
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = name.charCodeAt(i) + ((hash << 5) - hash);
  }

  // Generate two hue values for gradient
  const hue1 = Math.abs(hash % 360);
  const hue2 = (hue1 + 40) % 360; // Offset for second color

  return [`hsl(${hue1}, 40%, 25%)`, `hsl(${hue2}, 50%, 35%)`];
}

export function StartingAreaCard({ area, isSelected, onSelect }: StartingAreaCardProps) {
  const [color1, color2] = getGradientColors(area.name);
  const isAccessible = area.is_accessible;

  const cardContent = (
    <Card
      className={cn(
        'group relative cursor-pointer overflow-hidden transition-all duration-200',
        isSelected && 'ring-2 ring-primary ring-offset-2 ring-offset-background',
        !isAccessible && 'cursor-not-allowed opacity-60',
        isAccessible && !isSelected && 'hover:ring-1 hover:ring-primary/50'
      )}
      onClick={() => isAccessible && onSelect(area)}
    >
      {/* Crest image or gradient placeholder */}
      <div
        className="relative aspect-video w-full overflow-hidden"
        style={
          area.crest_image
            ? { backgroundImage: `url(${area.crest_image})`, backgroundSize: 'cover' }
            : { background: `linear-gradient(135deg, ${color1}, ${color2})` }
        }
      >
        {/* Area name overlay for placeholder */}
        {!area.crest_image && (
          <div className="absolute inset-0 flex items-center justify-center">
            <span className="text-4xl font-bold text-white/80 drop-shadow-lg">{area.name}</span>
          </div>
        )}

        {/* Selection indicator */}
        {isSelected && (
          <div className="absolute right-2 top-2">
            <CheckCircle2 className="h-6 w-6 text-primary drop-shadow-lg" />
          </div>
        )}

        {/* Lock icon for inaccessible areas */}
        {!isAccessible && (
          <div className="absolute inset-0 flex items-center justify-center bg-black/40">
            <Lock className="h-8 w-8 text-white/80" />
          </div>
        )}
      </div>

      <CardContent className="p-4">
        <h3 className="font-semibold">{area.name}</h3>
        {area.special_heritages.length > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">Special origins available</p>
        )}
      </CardContent>
    </Card>
  );

  // Wrap in HoverCard for description
  return (
    <HoverCard openDelay={300}>
      <HoverCardTrigger asChild>{cardContent}</HoverCardTrigger>
      <HoverCardContent className="w-80" side="right">
        <div className="space-y-2">
          <h4 className="font-semibold">{area.name}</h4>
          <p className="whitespace-pre-wrap text-sm text-muted-foreground">{area.description}</p>
          {area.special_heritages.length > 0 && (
            <div className="mt-2 border-t pt-2">
              <p className="text-xs font-medium text-muted-foreground">Special Heritage Options:</p>
              <ul className="mt-1 text-xs text-muted-foreground">
                {area.special_heritages.map((h) => (
                  <li key={h.id}>• {h.name}</li>
                ))}
              </ul>
            </div>
          )}
          {!isAccessible && (
            <p className="text-xs text-destructive">
              This area is not currently accessible to your account.
            </p>
          )}
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}
