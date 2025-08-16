import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useMyTenuresQuery } from '@/roster/queries';

interface Props {
  value: number | null;
  onChange: (value: number | null) => void;
  label?: string;
}

export function MyTenureSelect({ value, onChange, label = 'Sender' }: Props) {
  const { data: tenures } = useMyTenuresQuery();

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
          {tenures?.map((tenure) => (
            <SelectItem key={tenure.id} value={String(tenure.id)}>
              {tenure.display_name}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}

export default MyTenureSelect;
