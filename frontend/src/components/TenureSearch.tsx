import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { useTenureSearch } from '@/mail/queries';

interface Props {
  value: number | null;
  onChange: (value: number | null, display?: string) => void;
  label?: string;
}

export function TenureSearch({ value, onChange, label = 'Recipient' }: Props) {
  const [search, setSearch] = useState('');
  const { data: results } = useTenureSearch(search);

  return (
    <div className="w-64 space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <Input
        placeholder="Search character"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {results?.results.length ? (
        <ul className="rounded border">
          {results.results.map((opt) => (
            <li key={opt.id}>
              <Button
                type="button"
                variant={value === opt.id ? 'default' : 'ghost'}
                className="w-full justify-start"
                onClick={() => {
                  onChange(opt.id, opt.display_name);
                  setSearch(opt.display_name);
                }}
              >
                {opt.display_name}
              </Button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}

export default TenureSearch;
