import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useMyRosterEntriesQuery } from '@/roster/queries';

interface Props {
  value: number | null;
  onChange: (value: number | null) => void;
  label?: string;
}

export function MyTenureSelect({ value, onChange, label = 'Sender' }: Props) {
  const { data: entries } = useMyRosterEntriesQuery();

  return (
    <div className="w-64 space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <Select
        value={value ? String(value) : ''}
        onValueChange={(val) => onChange(val ? Number(val) : null)}
      >
        <SelectTrigger>
          <SelectValue placeholder="Select tenure" />
        </SelectTrigger>
        <SelectContent>
          {entries?.map((e) => (
            <SelectItem key={e.id} value={String(e.id)}>
              {e.name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default MyTenureSelect;
