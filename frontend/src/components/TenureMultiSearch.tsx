import { useState, useEffect } from 'react';
import AsyncSelect from 'react-select/async';
import { searchTenures } from '@/mail/api';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { Option } from '@/shared/types';

interface Props {
  value: Option<number>[];
  onChange: (value: Option<number>[]) => void;
  label?: string;
}

export function TenureMultiSearch({ value, onChange, label = 'Tenures' }: Props) {
  const [input, setInput] = useState('');
  const debounced = useDebouncedValue(input);
  const [options, setOptions] = useState<Option<number>[]>([]);

  useEffect(() => {
    searchTenures(debounced).then((res) =>
      setOptions(res.results.map((opt) => ({ value: opt.id, label: opt.display_name })))
    );
  }, [debounced]);

  return (
    <div className="w-64 space-y-1">
      <label className="text-sm font-medium">{label}</label>
      <AsyncSelect
        isMulti
        cacheOptions
        defaultOptions
        loadOptions={() => Promise.resolve(options)}
        value={value}
        onChange={(val) => onChange(val as Option<number>[])}
        onInputChange={(val) => {
          setInput(val);
          return val;
        }}
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
