import { useEffect, useState } from 'react';
import { useRostersQuery, useRosterEntriesQuery } from '../queries';
import type { RosterEntryData } from '../types';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { CharacterAvatarLink, CharacterLink } from '@/components/character';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { Gender, GENDER_LABELS } from '@/world/character_sheets/types';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';

export function RosterListPage() {
  const { data: rosters, isLoading: rostersLoading } = useRostersQuery();
  const [activeRoster, setActiveRoster] = useState<string>('');
  const [page, setPage] = useState(1);
  const [name, setName] = useState('');
  const [charClass, setCharClass] = useState('');
  const [gender, setGender] = useState<Gender | undefined>(undefined);

  const debouncedName = useDebouncedValue(name);
  const debouncedClass = useDebouncedValue(charClass);

  useEffect(() => {
    if (rosters && !activeRoster && rosters[0]) {
      setActiveRoster(String(rosters[0].id));
    }
  }, [rosters, activeRoster]);
  useEffect(() => {
    setPage(1);
  }, [debouncedName, debouncedClass, gender]);

  const { data: entryPage, isLoading: entriesLoading } = useRosterEntriesQuery(
    activeRoster ? Number(activeRoster) : undefined,
    page,
    {
      name: debouncedName,
      char_class: debouncedClass,
      gender,
    }
  );

  if (rostersLoading) return <p className="p-4">Loading...</p>;
  if (!rosters || rosters.length === 0) return <p className="p-4">No rosters found.</p>;

  return (
    <div className="container mx-auto space-y-4 p-4">
      <Tabs
        value={activeRoster}
        onValueChange={(v: string) => {
          setActiveRoster(v);
          setPage(1);
        }}
      >
        <TabsList>
          {rosters.map((r) => (
            <TabsTrigger key={r.id} value={String(r.id)}>
              {r.name}
            </TabsTrigger>
          ))}
        </TabsList>
        {rosters.map((r) => (
          <TabsContent key={r.id} value={String(r.id)}>
            <div className="mb-4 flex gap-2">
              <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
              <Input
                placeholder="Class"
                value={charClass}
                onChange={(e) => setCharClass(e.target.value)}
              />
              <Select
                value={gender ?? '__any__'}
                onValueChange={(v) => setGender(v === '__any__' ? undefined : (v as Gender))}
              >
                <SelectTrigger className="w-full">
                  <SelectValue placeholder="Gender" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__any__">Any</SelectItem>
                  {Object.entries(GENDER_LABELS).map(([value, label]) => (
                    <SelectItem key={value} value={value}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Portrait</TableHead>
                  <TableHead>Name</TableHead>
                  <TableHead>Gender</TableHead>
                  <TableHead>Class</TableHead>
                  <TableHead>Level</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {entriesLoading ? (
                  <TableRow>
                    <TableCell colSpan={5}>Loading...</TableCell>
                  </TableRow>
                ) : (
                  entryPage?.results?.map((entry: RosterEntryData) => (
                    <TableRow key={entry.id}>
                      <TableCell>
                        <CharacterAvatarLink
                          id={entry.id}
                          name={entry.character.name}
                          avatarUrl={entry.profile_picture?.media.cloudinary_url}
                          className="h-16 w-16"
                          fallback=""
                        />
                      </TableCell>
                      <TableCell>
                        <CharacterLink id={entry.id} className="underline">
                          {entry.character.name}
                        </CharacterLink>
                      </TableCell>
                      <TableCell>{entry.character.gender ?? '—'}</TableCell>
                      <TableCell>{entry.character.char_class ?? '—'}</TableCell>
                      <TableCell>{entry.character.level ?? '—'}</TableCell>
                    </TableRow>
                  ))
                )}
              </TableBody>
            </Table>
            <div className="mt-4 flex justify-between">
              <Button
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={!entryPage?.previous}
              >
                Previous
              </Button>
              <Button onClick={() => setPage((p) => p + 1)} disabled={!entryPage?.next}>
                Next
              </Button>
            </div>
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}
