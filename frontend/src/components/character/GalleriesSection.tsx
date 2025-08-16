import { Link } from 'react-router-dom';
import type { CharacterData } from '@/roster/types';

interface GalleriesSectionProps {
  galleries: CharacterData['galleries'];
}

export function GalleriesSection({ galleries }: GalleriesSectionProps) {
  return (
    <section>
      <h3 className="text-xl font-semibold">Galleries</h3>
      <ul className="list-disc pl-5">
        {galleries.map((g) => (
          <li key={g.name}>
            <Link to={g.url} className="text-primary underline">
              {g.name}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}
