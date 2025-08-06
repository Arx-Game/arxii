import { ChatWindow } from './ChatWindow';
import { CommandInput } from './CommandInput';
import { Card, CardContent } from '../../components/ui/card';

export function GameWindow() {
  return (
    <Card className="w-full max-w-[calc(88ch+2rem)]">
      <CardContent className="p-4">
        <ChatWindow />
        <CommandInput />
      </CardContent>
    </Card>
  );
}
