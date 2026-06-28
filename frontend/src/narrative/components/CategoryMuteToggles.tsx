/**
 * CategoryMuteToggles (#1522) — squelch whole narrative categories from the web.
 *
 * The web face of the telnet `weather squelch` toggle: a Switch per squelchable category. ON =
 * muted (the live push is suppressed; messages still land in the category's tab). Mirrors the
 * `MuteStoryToggle` bell, but keyed to a `NarrativeCategory` rather than a story.
 *
 * The squelchable set is deliberately small — only ambient, recurring pushes a player would want
 * to silence (currently the weather echo). Add a row here as new ambient categories appear.
 */

import { Switch } from '@/components/ui/switch';
import { Skeleton } from '@/components/ui/skeleton';

import { useCategoryMutes, useMuteCategory, useUnmuteCategory } from '../queries';
import type { NarrativeCategory, UserCategoryMute } from '../types';

interface SquelchableCategory {
  category: NarrativeCategory;
  label: string;
  description: string;
}

/** Ambient, recurring categories a player can silence. PLACEHOLDER copy. */
const SQUELCHABLE_CATEGORIES: SquelchableCategory[] = [
  {
    category: 'weather',
    label: 'Weather',
    description: 'Ambient weather echoes as conditions change around you.',
  },
];

interface CategoryToggleRowProps {
  config: SquelchableCategory;
  mute: UserCategoryMute | undefined;
}

function CategoryToggleRow({ config, mute }: CategoryToggleRowProps) {
  const muteCategory = useMuteCategory();
  const unmuteCategory = useUnmuteCategory();

  const isMuted = mute !== undefined;
  const isPending = muteCategory.isPending || unmuteCategory.isPending;

  const handleToggle = (nextMuted: boolean) => {
    if (nextMuted) {
      muteCategory.mutate({ category: config.category });
    } else if (mute) {
      unmuteCategory.mutate(mute.id);
    }
  };

  return (
    <div
      className="flex items-center justify-between rounded-lg border bg-card p-4"
      data-testid="category-mute-row"
    >
      <div className="space-y-0.5 pr-4">
        <p className="font-medium">{config.label}</p>
        <p className="text-xs text-muted-foreground">{config.description}</p>
      </div>
      <Switch
        checked={isMuted}
        disabled={isPending}
        onCheckedChange={handleToggle}
        aria-label={`Mute ${config.label} notifications`}
        data-testid="category-mute-switch"
      />
    </div>
  );
}

export function CategoryMuteToggles() {
  const { data, isLoading } = useCategoryMutes();

  if (isLoading) {
    return (
      <div className="space-y-3">
        {SQUELCHABLE_CATEGORIES.map((c) => (
          <div key={c.category} className="rounded-lg border bg-card p-4">
            <div className="flex items-center justify-between">
              <Skeleton className="h-5 w-40" />
              <Skeleton className="h-5 w-9" />
            </div>
          </div>
        ))}
      </div>
    );
  }

  const mutesByCategory = new Map<string, UserCategoryMute>(
    (data?.results ?? []).map((m) => [m.category, m])
  );

  return (
    <div className="space-y-3">
      {SQUELCHABLE_CATEGORIES.map((config) => (
        <CategoryToggleRow
          key={config.category}
          config={config}
          mute={mutesByCategory.get(config.category)}
        />
      ))}
    </div>
  );
}
