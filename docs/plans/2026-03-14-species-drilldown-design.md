# Species Selection Drill-Down Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the flat species grid in character creation with a two-level drill-down that groups subspecies under their parent species.

**Architecture:** Frontend-only change to HeritageStage.tsx. The existing API already returns parent/parent_name on each species. We group species client-side in a useMemo, add local selectedParent state, and conditionally render a top-level view or drill-down view.

**Tech Stack:** React, TypeScript, existing shadcn/ui Card components, Framer Motion.

---

## Current Problem

All playable species (leaf nodes) are shown in a flat 3-column grid. Subspecies like Khati variants sit alongside Human and Infernal with no visual grouping, creating a confusing sprawl.

## Design

### Data Grouping (no API changes)

The existing `useSpecies()` hook returns all playable species with `parent` (id | null) and `parent_name` (string | null). A `useMemo` groups `filteredSpecies` into:

- **Standalones:** Species with `parent === null` — directly selectable.
- **Parent groups:** `Map<number, { name: string, children: Species[] }>` — grouped by parent id.

### Interaction Flow

**Top-level view** (`selectedParent === null`):
- Grid shows standalone species cards + parent group cards.
- Standalone cards: click to select (sets `selected_species_id` on draft).
- Parent group cards: show parent name + "N subspecies →" in footer. Click sets `selectedParent` state (no draft mutation). If any child is currently selected, the parent card shows a checkmark.

**Drill-down view** (`selectedParent !== null`):
- Breadcrumb at top: "← All Species / Khati". Clicking "All Species" resets `selectedParent` to null.
- Grid shows subspecies for that parent using existing `SpeciesCard` component.
- Clicking a subspecies selects it (sets `selected_species_id`).

**Edge cases:**
- Changing beginnings clears species selection (existing behavior) and resets `selectedParent` to null.

### Component Changes

**HeritageStage.tsx** (only file changed):
- `useState<number | null>(null)` for `selectedParent`.
- `useMemo` to compute grouping from `filteredSpecies`.
- `useEffect` to reset `selectedParent` when beginnings changes.
- Conditional render: top-level view or drill-down view.
- New local `SpeciesGroupCard` component (~30 lines) — same style as SpeciesCard but shows parent name + child count + "→" indicator.

**No changes to:** SpeciesCard.tsx, api.ts, queries.ts, types.ts, backend.

---

### Task 1: Add species grouping logic

**Files:**
- Modify: `frontend/src/character-creation/components/HeritageStage.tsx`

**Step 1: Add the grouping useMemo and selectedParent state**

Add after the existing `filteredSpecies` computation:

```tsx
const [selectedParent, setSelectedParent] = useState<number | null>(null);

const speciesGroups = useMemo(() => {
  const standalones: Species[] = [];
  const parentGroups = new Map<number, { name: string; children: Species[] }>();

  for (const species of filteredSpecies ?? []) {
    if (!species.parent) {
      standalones.push(species);
    } else {
      const group = parentGroups.get(species.parent);
      if (group) {
        group.children.push(species);
      } else {
        parentGroups.set(species.parent, {
          name: species.parent_name ?? 'Unknown',
          children: [species],
        });
      }
    }
  }

  return { standalones, parentGroups };
}, [filteredSpecies]);
```

**Step 2: Add useEffect to reset selectedParent when beginnings changes**

```tsx
const selectedBeginningsId = draft.selected_beginnings?.id;
useEffect(() => {
  setSelectedParent(null);
}, [selectedBeginningsId]);
```

**Step 3: Add useMemo import if missing, add useEffect import if missing**

Verify `useState`, `useMemo`, `useEffect` are all imported from React.

**Step 4: Run typecheck**

Run: `pnpm typecheck`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/character-creation/components/HeritageStage.tsx
git commit -m "feat(cg): add species grouping logic for drill-down"
```

---

### Task 2: Create SpeciesGroupCard component

**Files:**
- Modify: `frontend/src/character-creation/components/HeritageStage.tsx`

**Step 1: Add SpeciesGroupCard as a local component**

Add alongside existing SpeciesDetailPanel and BeginningsDetailPanel:

```tsx
function SpeciesGroupCard({
  parentName,
  childCount,
  isChildSelected,
  onClick,
  onHover,
}: {
  parentName: string;
  childCount: number;
  isChildSelected: boolean;
  onClick: () => void;
  onHover?: (species: Species | null) => void;
}) {
  return (
    <Card
      className={cn(
        'relative cursor-pointer transition-all',
        isChildSelected && 'ring-2 ring-primary',
        !isChildSelected && 'hover:ring-1 hover:ring-primary/50'
      )}
      onClick={onClick}
      onMouseEnter={() => onHover?.(null)}
      onMouseLeave={() => onHover?.(null)}
    >
      {isChildSelected && (
        <div className="absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground">
          <Check className="h-4 w-4" />
        </div>
      )}

      <CardHeader className="pb-3">
        <CardTitle className="text-lg">{parentName}</CardTitle>
      </CardHeader>

      <CardContent>
        <p className="text-sm text-muted-foreground">
          {childCount} subspecies{' '}
          <span className="text-primary">→</span>
        </p>
      </CardContent>
    </Card>
  );
}
```

**Step 2: Run typecheck**

Run: `pnpm typecheck`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/character-creation/components/HeritageStage.tsx
git commit -m "feat(cg): add SpeciesGroupCard component for parent species"
```

---

### Task 3: Replace flat species grid with grouped top-level / drill-down views

**Files:**
- Modify: `frontend/src/character-creation/components/HeritageStage.tsx`

**Step 1: Add ChevronLeft import**

Add `ChevronLeft` to the lucide-react import alongside `CheckCircle2`.

**Step 2: Replace the species grid section**

Replace the section inside `{draft.selected_beginnings && (...)}` that renders the species grid. The new version conditionally renders based on `selectedParent`:

```tsx
{draft.selected_beginnings && (
  <section className="space-y-4">
    <div>
      <h3 className="theme-heading text-lg font-semibold">
        {copy?.heritage_species_heading ?? ''}
      </h3>
      <p className="text-sm text-muted-foreground">{copy?.heritage_species_desc ?? ''}</p>
    </div>
    {speciesLoading ? (
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="h-40 animate-pulse rounded-lg bg-muted" />
        <div className="h-40 animate-pulse rounded-lg bg-muted" />
      </div>
    ) : selectedParent === null ? (
      <>
        {/* Top-level: standalones + parent groups */}
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {speciesGroups.standalones.map((species) => (
            <SpeciesCard
              key={species.id}
              species={species}
              isSelected={draft.selected_species?.id === species.id}
              onSelect={() => handleSpeciesSelect(species.id)}
              disabled={remainingPoints < 0 && draft.selected_species?.id !== species.id}
              onHover={setHoveredSpecies}
            />
          ))}
          {Array.from(speciesGroups.parentGroups.entries()).map(
            ([parentId, { name, children }]) => (
              <SpeciesGroupCard
                key={`parent-${parentId}`}
                parentName={name}
                childCount={children.length}
                isChildSelected={children.some(
                  (c) => c.id === draft.selected_species?.id
                )}
                onClick={() => setSelectedParent(parentId)}
              />
            )
          )}
          {speciesGroups.standalones.length === 0 &&
            speciesGroups.parentGroups.size === 0 && (
              <Card>
                <CardContent className="py-8">
                  <p className="text-center text-sm text-muted-foreground">
                    No species available for this beginnings path.
                  </p>
                </CardContent>
              </Card>
            )}
        </div>

        {/* Mobile: Species detail below cards */}
        {draft.selected_species && (
          <div className="mt-2 lg:hidden">
            <SpeciesDetailPanel species={draft.selected_species} />
          </div>
        )}
      </>
    ) : (
      <>
        {/* Drill-down: breadcrumb + subspecies */}
        <button
          type="button"
          className="flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          onClick={() => setSelectedParent(null)}
        >
          <ChevronLeft className="h-4 w-4" />
          All Species
          <span className="mx-1 text-muted-foreground/50">/</span>
          <span className="text-foreground">
            {speciesGroups.parentGroups.get(selectedParent)?.name}
          </span>
        </button>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {speciesGroups.parentGroups
            .get(selectedParent)
            ?.children.map((species) => (
              <SpeciesCard
                key={species.id}
                species={species}
                isSelected={draft.selected_species?.id === species.id}
                onSelect={() => handleSpeciesSelect(species.id)}
                disabled={
                  remainingPoints < 0 && draft.selected_species?.id !== species.id
                }
                onHover={setHoveredSpecies}
              />
            ))}
        </div>

        {/* Mobile: Species detail below cards */}
        {draft.selected_species && (
          <div className="mt-2 lg:hidden">
            <SpeciesDetailPanel species={draft.selected_species} />
          </div>
        )}
      </>
    )}
  </section>
)}
```

**Step 3: Run typecheck**

Run: `pnpm typecheck`
Expected: PASS

**Step 4: Run lint**

Run: `pnpm lint`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/character-creation/components/HeritageStage.tsx
git commit -m "feat(cg): replace flat species grid with parent drill-down UX"
```
