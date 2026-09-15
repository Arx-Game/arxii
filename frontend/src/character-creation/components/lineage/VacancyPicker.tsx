/** Openings on a staff family, with the two importance axes and the price (#3648). */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CharacterDraft, Vacancy } from '../../types';

interface Props {
  draft: CharacterDraft;
  vacancies: Vacancy[];
  onPick: (vacancyId: number | null) => void;
}

function capacityLabel(v: Vacancy): string {
  if (v.count_remaining === null) return 'Standing';
  return `${v.count_remaining} left`;
}

export function VacancyPicker({ draft, vacancies, onPick }: Props) {
  if (vacancies.length === 0) return null;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {vacancies.map((vacancy) => {
        const chosen = draft.selected_vacancy === vacancy.id;
        return (
          <button
            key={vacancy.id}
            type="button"
            aria-pressed={chosen}
            onClick={() => onPick(chosen ? null : vacancy.id)}
            className={cn(
              'rounded-md border p-3 text-left text-sm transition-colors',
              chosen ? 'border-primary bg-primary/10' : 'hover:bg-muted/50'
            )}
          >
            <span className="flex items-center justify-between gap-2">
              <span className="font-medium">{vacancy.name}</span>
              <Badge variant="outline">{vacancy.cost === 0 ? 'Free' : `${vacancy.cost} pts`}</Badge>
            </span>
            {vacancy.description && (
              <span className="block text-xs text-muted-foreground">{vacancy.description}</span>
            )}
            <span className="mt-1 flex flex-wrap gap-1 text-xs">
              <Badge variant="secondary">Importance {vacancy.importance}</Badge>
              <Badge variant="secondary">Presumed {vacancy.presumed_importance}</Badge>
              <Badge variant="secondary">{vacancy.basis === 'kin' ? 'Kin' : 'Retainer'}</Badge>
              <Badge variant="secondary">{capacityLabel(vacancy)}</Badge>
              {vacancy.rank_name && <Badge variant="secondary">{vacancy.rank_name}</Badge>}
            </span>
            {vacancy.kin_pool && (
              <span className="block text-xs text-muted-foreground">
                {vacancy.kin_pool.description}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
