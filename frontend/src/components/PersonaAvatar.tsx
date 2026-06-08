import { cn } from '@/lib/utils';

export interface PersonaAvatarSource {
  name: string;
  thumbnailUrl?: string | null;
  // Resolved PlayerMedia URL when persona.thumbnail FK is set.
  // Backend serializer resolves this; frontend doesn't fetch the FK separately.
  thumbnailMediaUrl?: string | null;
}

interface PersonaAvatarProps {
  source: PersonaAvatarSource;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

function initialLetter(name: string): string {
  return (name.trim()[0] ?? '?').toUpperCase();
}

function colorForName(name: string): string {
  // Stable hash -> HSL color so the same persona always gets the same color.
  let hash = 0;
  for (let i = 0; i < name.length; i++) hash = Math.trunc(hash * 31 + name.charCodeAt(i));
  const hue = Math.abs(hash) % 360;
  return `hsl(${hue}, 55%, 35%)`;
}

const SIZE_CLASSES = {
  sm: 'h-6 w-6 text-[10px]',
  md: 'h-8 w-8 text-xs',
  lg: 'h-12 w-12 text-base',
} as const;

export function PersonaAvatar({ source, size = 'md', className }: PersonaAvatarProps) {
  const url = source.thumbnailMediaUrl ?? source.thumbnailUrl ?? null;
  const cls = cn(
    'rounded-full overflow-hidden flex items-center justify-center font-semibold text-white shrink-0',
    SIZE_CLASSES[size],
    className
  );

  if (url) {
    return (
      <span className={cls} style={{ background: colorForName(source.name) }}>
        <img src={url} alt={source.name} className="h-full w-full object-cover" />
      </span>
    );
  }
  return (
    <span className={cls} style={{ background: colorForName(source.name) }}>
      {initialLetter(source.name)}
    </span>
  );
}
