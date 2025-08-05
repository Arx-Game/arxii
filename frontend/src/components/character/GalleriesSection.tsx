import type { CharacterGallery } from '../../evennia_replacements/types';

interface GalleriesSectionProps {
  galleries: CharacterGallery[];
}

export function GalleriesSection({ galleries }: GalleriesSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Galleries</h3>
      <ul className="list-disc pl-5">
        {galleries.map((g) => (
          <li key={g.name}>
            <a href={g.url} className="text-primary underline">
              {g.name}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}
