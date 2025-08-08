import type { CharacterData } from '../../roster/types';

interface BackgroundSectionProps {
  background?: CharacterData['background'];
}

export function BackgroundSection({ background }: BackgroundSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Background</h3>
      <p>{background || 'TBD'}</p>
    </section>
  );
}
