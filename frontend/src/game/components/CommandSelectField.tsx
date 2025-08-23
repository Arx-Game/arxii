import { Label } from '@/components/ui/label';
import SearchSelect from '@/components/SearchSelect';

interface CommandSelectFieldProps {
  param: string;
  endpoint: string;
  value: string;
  onChange: (value: string) => void;
}

export function CommandSelectField({ param, endpoint, value, onChange }: CommandSelectFieldProps) {
  return (
    <div className="grid gap-2">
      <Label htmlFor={param}>{param}</Label>
      <SearchSelect endpoint={endpoint} value={value} onChange={onChange} />
    </div>
  );
}
