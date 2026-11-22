/**
 * The ink an affinity is written in (#5280, the approved demo's Primal, Abyssal and Celestial
 * colours): a Tailwind text pair for light and dark. A resonance of an unknown affinity gets no
 * colour. The `--aura-*` tokens are literals for the halo and load only with the character
 * sheet's stylesheet, so they are not used here.
 */
const AFFINITY_INK: Record<string, string> = {
  Primal: 'text-orange-700 dark:text-orange-400',
  Abyssal: 'text-violet-700 dark:text-violet-400',
  Celestial: 'text-cyan-700 dark:text-cyan-300',
};

export function affinityInkClass(affinityName: string | null | undefined): string {
  return (affinityName && AFFINITY_INK[affinityName]) || '';
}
