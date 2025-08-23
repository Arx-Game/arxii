import { useState, useEffect } from 'react';
import AsyncSelect from 'react-select/async';
import type { OptionsOrGroups, GroupBase } from 'react-select';
import { apiFetch } from '@/evennia_replacements/api';
import { useDebouncedValue } from '@/hooks/useDebouncedValue';
import type { Option } from '@/shared/types';

interface SearchSelectProps {
  endpoint: string;
  value: string;
  onChange: (val: string) => void;
}

export function SearchSelect({ endpoint, value, onChange }: SearchSelectProps) {
  const [input, setInput] = useState('');
  const debounced = useDebouncedValue(input);
  const [options, setOptions] = useState<Option[]>([]);

  useEffect(() => {
    const url = new URL(endpoint, window.location.origin);
    url.searchParams.set('search', debounced);
    url.searchParams.set('page_size', '10');
    url.searchParams.set('ordering', 'label');
    apiFetch(url.pathname + url.search)
      .then((res) => res.json())
      .then((data: OptionsOrGroups<Option, GroupBase<Option>>) => {
        setOptions(data as Option[]);
      });
  }, [endpoint, debounced]);

  return (
    <AsyncSelect
      cacheOptions
      defaultOptions={options}
      loadOptions={() => Promise.resolve(options)}
      value={value ? { value, label: value } : null}
      onInputChange={(val) => {
        setInput(val);
        return val;
      }}
      onChange={(opt) => onChange((opt as Option | null)?.value ?? '')}
      classNames={{
        control: () =>
          'bg-white text-black dark:bg-slate-800 dark:text-white border border-slate-300 dark:border-slate-600',
        menu: () =>
          'bg-white text-black dark:bg-slate-800 dark:text-white border border-slate-300 dark:border-slate-600',
        option: (state) =>
          state.isFocused
            ? 'bg-slate-100 dark:bg-slate-700 text-black dark:text-white'
            : 'text-black dark:text-white',
        input: () => 'text-black dark:text-white',
        singleValue: () => 'text-black dark:text-white',
        placeholder: () => 'text-slate-500 dark:text-slate-400',
      }}
    />
  );
}

export default SearchSelect;
