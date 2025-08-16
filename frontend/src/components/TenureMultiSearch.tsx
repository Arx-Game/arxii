import AsyncSelect from 'react-select/async';
import type { OptionsOrGroups, GroupBase } from 'react-select';
import { searchTenures } from '@/mail/api';

interface Option {
  value: number;
  label: string;
}

interface Props {
  value: Option[];
  onChange: (value: Option[]) => void;
  label?: string;
}

function loadTenureOptions(
  inputValue: string
): Promise<OptionsOrGroups<Option, GroupBase<Option>>> {
  return searchTenures(inputValue).then((res) =>
    res.results.map((opt) => ({ value: opt.id, label: opt.display_name }))
  );
}

export function TenureMultiSearch({ value, onChange, label = 'Tenures' }: Props) {
  return (
    <div className="w-64 space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <AsyncSelect
        isMulti
        cacheOptions
        defaultOptions
        loadOptions={loadTenureOptions}
        value={value}
        onChange={(val) => onChange(val as Option[])}
        classNames={{
          control: () => 'bg-white text-black dark:bg-slate-800 dark:text-white',
          menu: () => 'bg-white text-black dark:bg-slate-800 dark:text-white',
          option: (state) =>
            state.isFocused
              ? 'bg-slate-100 dark:bg-slate-700 text-black dark:text-white'
              : 'text-black dark:text-white',
          multiValue: () => 'bg-slate-200 dark:bg-slate-700',
          multiValueLabel: () => 'text-black dark:text-white',
          multiValueRemove: () =>
            'text-black dark:text-white hover:bg-slate-300 dark:hover:bg-slate-600',
        }}
      />
    </div>
  );
}

export default TenureMultiSearch;
