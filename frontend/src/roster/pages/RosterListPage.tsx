import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useRostersQuery, useRosterEntriesQuery } from '../queries';
import type { RosterEntryData } from '../types';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '../../components/ui/tabs';
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '../../components/ui/table';
import { Input } from '../../components/ui/input';
import { Button } from '../../components/ui/button';

export function RosterListPage() {
  const { data: rosters, isLoading: rostersLoading } = useRostersQuery();
  const [activeRoster, setActiveRoster] = useState<number | undefined>(undefined);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState({ name: '', char_class: '', gender: '' });

  useEffect(() => {
    if (rosters && activeRoster === undefined) {
      setActiveRoster(rosters[0]?.id);
    }
  }, [rosters, activeRoster]);

  const { data: entryPage, isLoading: entriesLoading } = useRosterEntriesQuery(
    activeRoster,
    page,
    filters
  );

  if (rostersLoading) return <p className="p-4">Loading...</p>;
  if (!rosters || rosters.length === 0) return <p className="p-4">No rosters found.</p>;

  const handleFilterChange = (key: 'name' | 'char_class' | 'gender', value: string) => {
    setPage(1);
    setFilters((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <div className="container mx-auto space-y-4 p-4">
      <Tabs
        value={activeRoster ? String(activeRoster) : undefined}
        onValueChange={(v: string) => {
          setActiveRoster(Number(v));
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
              <Input
                placeholder="Name"
                value={filters.name}
                onChange={(e) => handleFilterChange('name', e.target.value)}
              />
              <Input
                placeholder="Class"
                value={filters.char_class}
                onChange={(e) => handleFilterChange('char_class', e.target.value)}
              />
              <Input
                placeholder="Gender"
                value={filters.gender}
                onChange={(e) => handleFilterChange('gender', e.target.value)}
              />
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
                        <Link to={`/characters/${entry.id}`}>
                          {entry.profile_picture ? (
                            <img
                              src={entry.profile_picture.media.cloudinary_url}
                              alt={entry.character.name}
                              className="h-16 w-16 object-cover"
                            />
                          ) : (
                            <div className="h-16 w-16 bg-gray-200" />
                          )}
                        </Link>
                      </TableCell>
                      <TableCell>
                        <Link to={`/characters/${entry.id}`} className="underline">
                          {entry.character.name}
                        </Link>
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
