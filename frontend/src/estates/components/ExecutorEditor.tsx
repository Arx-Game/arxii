import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { searchPersonas } from '@/events/queries';
import type { Will } from '../estatesQueries';
import type { useWillMutations } from '../estatesQueries';

interface ExecutorEditorProps {
  will: Will;
  frozen: boolean;
  mutations: ReturnType<typeof useWillMutations>;
}

export function ExecutorEditor({ will, frozen, mutations }: ExecutorEditorProps) {
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<{ id: number; name: string }[]>([]);

  const search = async (value: string) => {
    setQuery(value);
    if (value.length < 2) {
      setMatches([]);
      return;
    }
    setMatches((await searchPersonas(value)).slice(0, 5));
  };

  return (
    <section className="space-y-2">
      <h3 className="text-xl font-semibold">Executors</h3>
      <p className="text-sm text-muted-foreground">
        Anyone named here may hold your will-reading after your death.
      </p>
      <ul className="space-y-1">
        {will.executors.map((executor) => (
          <li
            key={executor.id}
            className="flex items-center justify-between rounded border p-2 text-sm"
          >
            <span>{executor.persona_name}</span>
            {!frozen && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => mutations.removeExecutor.mutate(executor.id)}
              >
                Remove
              </Button>
            )}
          </li>
        ))}
        {will.executors.length === 0 && (
          <li className="text-sm text-muted-foreground">No executors named.</li>
        )}
      </ul>
      {!frozen && (
        <div className="space-y-2">
          <Input
            placeholder="Search characters…"
            value={query}
            onChange={(e) => void search(e.target.value)}
          />
          {matches.length > 0 && (
            <ul className="rounded border text-sm">
              {matches.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    className="w-full p-1 text-left hover:bg-accent"
                    onClick={() => {
                      mutations.addExecutor.mutate({ willId: will.id, personaId: m.id });
                      setQuery('');
                      setMatches([]);
                    }}
                  >
                    {m.name}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
