import { useState, FormEvent } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import type { CommandSpec } from '@/game/types';
import type { MyRosterEntry } from '@/roster/types';
import { formatCommand } from '@/game/helpers/commandHelpers';
import {
  Sheet,
  SheetTrigger,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
  SheetFooter,
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';

interface CommandDrawerProps extends CommandSpec {
  character: MyRosterEntry['name'];
}

export function CommandDrawer({
  character,
  action,
  prompt,
  params_schema,
  name,
  help,
}: CommandDrawerProps) {
  const { send } = useGameSocket();
  const [fields, setFields] = useState<Record<string, string>>({});

  const handleChange = (param: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    setFields({ ...fields, [param]: e.target.value });
  };

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    const cmd = formatCommand(prompt, fields);
    send(character, cmd);
    setFields({});
  };

  const title = name ?? action;
  const description = help ?? prompt;

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="ghost" className="justify-start px-2 py-1">
          {title}
        </Button>
      </SheetTrigger>
      <SheetContent className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <form onSubmit={handleSubmit} className="mt-4 space-y-4">
          {Object.keys(params_schema).map((param) => (
            <div key={param} className="grid gap-2">
              <Label htmlFor={param}>{param}</Label>
              <input
                id={param}
                type="text"
                value={fields[param] ?? ''}
                onChange={handleChange(param)}
                className="w-full rounded border p-2"
              />
            </div>
          ))}
          <SheetFooter>
            <Button type="submit">Submit</Button>
          </SheetFooter>
        </form>
      </SheetContent>
    </Sheet>
  );
}
