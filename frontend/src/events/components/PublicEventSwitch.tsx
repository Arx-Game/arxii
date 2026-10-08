import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

interface PublicEventSwitchProps {
  id: string;
  checked: boolean;
  onCheckedChange: (next: boolean) => void;
}

/** The row every event form shares: the switch and its one word (#4193). */
export function PublicEventSwitch({ id, checked, onCheckedChange }: PublicEventSwitchProps) {
  return (
    <div className="flex items-center gap-3">
      <Switch id={id} checked={checked} onCheckedChange={onCheckedChange} />
      <Label htmlFor={id}>Public event</Label>
    </div>
  );
}
