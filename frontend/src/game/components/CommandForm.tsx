import { useState, FormEvent } from 'react';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { SheetFooter } from '@/components/ui/sheet';
import type { CommandSpec } from '@/game/types';
import SearchSelect from '@/components/SearchSelect';

interface CommandFormProps {
  params_schema: CommandSpec['params_schema'];
  onSubmit: (fields: Record<string, string>) => void;
  closeOnSubmit: boolean;
  setCloseOnSubmit: (close: boolean) => void;
}

export function CommandForm({
  params_schema,
  onSubmit,
  closeOnSubmit,
  setCloseOnSubmit,
}: CommandFormProps) {
  const [fields, setFields] = useState<Record<string, string>>({});

  const handleChange = (param: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields({ ...fields, [param]: e.target.value });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    onSubmit(fields);
    setFields({});
  };

  return (
    <form onSubmit={handleSubmit} className="mt-4 space-y-4">
      {Object.keys(params_schema).map((param) => {
        const schema = params_schema[param];
        const isSelect = schema.widget === 'character-search' && schema.options_endpoint;
        return (
          <div key={param} className="grid gap-2">
            <Label htmlFor={param}>{param}</Label>
            {isSelect ? (
              <SearchSelect
                endpoint={schema.options_endpoint!}
                value={fields[param] ?? ''}
                onChange={(val) => setFields({ ...fields, [param]: val })}
              />
            ) : (
              <input
                id={param}
                type="text"
                value={fields[param] ?? ''}
                onChange={handleChange(param)}
                className="w-full rounded border p-2"
              />
            )}
          </div>
        );
      })}
      <div className="flex items-center space-x-2">
        <input
          id="close-on-submit"
          type="checkbox"
          checked={closeOnSubmit}
          onChange={(e) => setCloseOnSubmit(e.target.checked)}
          className="h-4 w-4"
        />
        <Label htmlFor="close-on-submit">Close on submit</Label>
      </div>
      <SheetFooter>
        <Button type="submit">Submit</Button>
      </SheetFooter>
    </form>
  );
}
