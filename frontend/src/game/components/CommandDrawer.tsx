import { useState } from 'react';
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
} from '@/components/ui/sheet';
import { Button } from '@/components/ui/button';
import { CommandForm } from './CommandForm';

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
  const [open, setOpen] = useState(false);
  const [closeOnSubmit, setCloseOnSubmit] = useState(true);

  const handleSubmit = (fields: Record<string, string>) => {
    const cmd = formatCommand(prompt, fields);
    send(character, cmd);
    if (closeOnSubmit) {
      setOpen(false);
    }
  };

  const title = name ?? action;
  const description = help ?? prompt;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" className="justify-start px-2 py-1">
          {title}
        </Button>
      </SheetTrigger>
      <SheetContent hideOverlay className="sm:max-w-md">
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          {description && <SheetDescription>{description}</SheetDescription>}
        </SheetHeader>
        <CommandForm
          params_schema={params_schema}
          onSubmit={handleSubmit}
          closeOnSubmit={closeOnSubmit}
          setCloseOnSubmit={setCloseOnSubmit}
        />
      </SheetContent>
    </Sheet>
  );
}
