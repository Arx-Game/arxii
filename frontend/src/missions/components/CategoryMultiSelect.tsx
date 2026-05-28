/**
 * Reusable category picker — checkbox list backed by useMissionCategories.
 * Used by CreateMissionPage and EditCategoriesDialog. Value is a list of
 * MissionCategory primary keys; onChange receives the new list.
 *
 * Uses a plain <input type="checkbox"> (aria-label on the input) because
 * the project does not include a shadcn Checkbox primitive.
 */

import { useMissionCategories } from '../queries';

interface CategoryMultiSelectProps {
  value: readonly number[];
  onChange: (next: number[]) => void;
}

export function CategoryMultiSelect({ value, onChange }: CategoryMultiSelectProps) {
  const { data, isLoading, isError } = useMissionCategories();

  if (isLoading) {
    return <div className="text-xs text-muted-foreground">Loading categories…</div>;
  }

  if (isError) {
    return <div className="text-xs text-destructive">Failed to load categories.</div>;
  }

  const categories = data?.results ?? [];

  if (categories.length === 0) {
    return <div className="text-xs text-muted-foreground">No categories available.</div>;
  }

  const selected = new Set(value);

  const toggle = (id: number) => {
    if (selected.has(id)) {
      onChange(value.filter((v) => v !== id));
    } else {
      onChange([...value, id]);
    }
  };

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {categories.map((cat) => (
        <label
          key={cat.id}
          className="flex cursor-pointer items-center gap-2 rounded border px-2 py-1 text-sm"
        >
          <input
            type="checkbox"
            checked={selected.has(cat.id)}
            onChange={() => toggle(cat.id)}
            aria-label={cat.name}
            className="h-3.5 w-3.5 rounded border-border accent-primary"
          />
          {cat.name}
        </label>
      ))}
    </div>
  );
}
