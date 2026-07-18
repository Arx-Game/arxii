/**
 * PetitionPage (#2288) — the emergency door of the three staff-contact doors
 * (feedback and conduct reports are the other two; both linked below).
 *
 * Structured, near-zero free text: a category picker, the reference the
 * category requires (your character, or the scene), and a short capped
 * description. One open petition per account — the structural rate-limit
 * that keeps "emergency" legible.
 */

import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import { fetchMyPetitions, submitPetition } from '@/submissions/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { useMyRosterEntriesQuery } from '@/roster/queries';

interface CategoryOption {
  value: string;
  label: string;
  hint: string;
  /** Which reference the category requires: own character, a scene id, or nothing. */
  requires: 'character' | 'scene' | null;
}

// Mirrors PetitionCategory + _CATEGORY_REQUIRES on the backend (#2288).
const CATEGORIES: CategoryOption[] = [
  {
    value: 'unfair_death',
    label: 'Unfair / Unjustified Death',
    hint: 'Your character died in a way you believe broke the rules of the system or the scene.',
    requires: 'character',
  },
  {
    value: 'scene_conduct',
    label: 'Scene Turning OOC-Hostile',
    hint: 'A scene in progress is turning hostile out-of-character and needs staff eyes now.',
    requires: 'scene',
  },
  {
    value: 'stuck_unplayable',
    label: 'Character Stuck / Unplayable',
    hint: 'Your character is wedged somewhere no game action can recover them from.',
    requires: 'character',
  },
  {
    value: 'other_emergency',
    label: 'Other Emergency',
    hint: 'Something urgent that fits none of the above. Non-emergencies belong in feedback.',
    requires: null,
  },
];

const OPEN_STATUS = 'open';

export function PetitionPage() {
  const qc = useQueryClient();
  const [category, setCategory] = useState<CategoryOption>(CATEGORIES[0]);
  const [description, setDescription] = useState('');
  const [characterId, setCharacterId] = useState<number | null>(null);
  const [sceneId, setSceneId] = useState('');

  const { data: characters = [] } = useMyRosterEntriesQuery(true);
  const { data: petitions = [], isLoading } = useQuery({
    queryKey: ['my-petitions'],
    queryFn: fetchMyPetitions,
  });

  const mutation = useMutation({
    mutationFn: submitPetition,
    onSuccess: () => {
      setDescription('');
      qc.invalidateQueries({ queryKey: ['my-petitions'] }).catch(() => {});
    },
  });

  const openPetition = petitions.find((p) => p.status === OPEN_STATUS) ?? null;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!description.trim()) return;
    mutation.mutate({
      category: category.value,
      description: description.trim(),
      subject_character:
        category.requires === 'character'
          ? (characterId ?? characters[0]?.character_id ?? null)
          : null,
      scene: category.requires === 'scene' && /^\d+$/.test(sceneId) ? Number(sceneId) : null,
    });
  }

  return (
    <div className="container mx-auto max-w-2xl space-y-6 px-4 py-8">
      <Card>
        <CardHeader>
          <CardTitle>Petition Staff (Emergency)</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <p className="text-sm text-muted-foreground">
            This is the emergency line: something is wrong right now and needs a staff decision. For
            everything else, use{' '}
            <Link className="underline" to="/feedback">
              feedback
            </Link>
            ; to report another player&apos;s conduct, use the{' '}
            <Link className="underline" to="/report-player">
              conduct report
            </Link>
            . You can hold one open petition at a time.
          </p>
          {openPetition ? (
            <p className="text-sm" data-testid="open-petition-notice">
              You already have an open petition ({openPetition.category_display}) filed{' '}
              {new Date(openPetition.created_at).toLocaleString()}. Staff will get to it as soon as
              they can.
            </p>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="space-y-2">
                {CATEGORIES.map((option) => (
                  <label key={option.value} className="flex cursor-pointer items-start gap-2">
                    <input
                      type="radio"
                      name="category"
                      className="mt-1"
                      checked={category.value === option.value}
                      onChange={() => setCategory(option)}
                    />
                    <span>
                      <span className="font-medium">{option.label}</span>
                      <span className="block text-xs text-muted-foreground">{option.hint}</span>
                    </span>
                  </label>
                ))}
              </div>
              {category.requires === 'character' && characters.length > 1 && (
                <label className="block text-sm">
                  Which character:
                  <select
                    className="ml-2 rounded border bg-background p-1"
                    value={characterId ?? characters[0]?.character_id ?? ''}
                    onChange={(e) => setCharacterId(Number(e.target.value))}
                  >
                    {characters.map((entry) => (
                      <option key={entry.id} value={entry.character_id ?? ''}>
                        {entry.name}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              {category.requires === 'scene' && (
                <label className="block text-sm">
                  Scene number (from the scene page URL):
                  <input
                    type="text"
                    inputMode="numeric"
                    className="ml-2 w-24 rounded border bg-background p-1"
                    value={sceneId}
                    onChange={(e) => setSceneId(e.target.value)}
                  />
                </label>
              )}
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="What happened, and what needs a staff decision? Short and specific."
                rows={5}
                maxLength={1000}
                disabled={mutation.isPending}
              />
              {mutation.isError && mutation.error instanceof Error && (
                <p className="text-sm text-destructive">{mutation.error.message}</p>
              )}
              <div className="flex justify-end">
                <Button
                  type="submit"
                  disabled={
                    mutation.isPending ||
                    !description.trim() ||
                    (category.requires === 'scene' && !/^\d+$/.test(sceneId))
                  }
                >
                  {mutation.isPending ? 'Filing...' : 'File petition'}
                </Button>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
      {!isLoading && petitions.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Your petitions</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2">
              {petitions.map((p) => (
                <li key={p.id} className="rounded border p-2 text-sm" data-testid="petition-row">
                  <span className="font-medium">{p.category_display}</span>
                  <span className="ml-2 text-xs uppercase text-muted-foreground">{p.status}</span>
                  <p className="text-muted-foreground">{p.description}</p>
                  {p.staff_notes && (
                    <p className="mt-1 text-xs">
                      <span className="font-medium">Staff:</span> {p.staff_notes}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
