import { useQuery } from '@tanstack/react-query';
import type { CSSProperties } from 'react';
import { apiFetch } from '@/evennia_replacements/api';
import { getGradientColors } from '@/character-creation/components/StartingAreaCard';

export type PageBackgroundSlot = 'homepage' | 'roster' | 'cg_stage' | 'game_client';

export interface PageBackground {
  slot: PageBackgroundSlot;
  art_url: string | null;
}

async function fetchPageBackgrounds(): Promise<PageBackground[]> {
  const res = await apiFetch('/api/backgrounds/');
  if (!res.ok) {
    throw new Error('Failed to load page backgrounds');
  }
  return res.json();
}

export function usePageBackgrounds() {
  return useQuery({
    queryKey: ['page-backgrounds'],
    queryFn: fetchPageBackgrounds,
    staleTime: 5 * 60 * 1000,
  });
}

export function pageBackgroundStyle(
  backgrounds: PageBackground[] | undefined,
  slot: PageBackgroundSlot,
  gradientSeed: string
): CSSProperties {
  const artUrl = backgrounds?.find((b) => b.slot === slot)?.art_url;
  if (artUrl) {
    return { backgroundImage: `url(${artUrl})`, backgroundSize: 'cover' };
  }
  const [color1, color2] = getGradientColors(gradientSeed);
  return { background: `linear-gradient(135deg, ${color1}, ${color2})` };
}
