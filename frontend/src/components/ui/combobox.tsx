import * as React from 'react';
import { Command } from 'cmdk';
import { Check, ChevronsUpDown } from 'lucide-react';

import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';

export interface ComboboxItem {
  value: string;
  label: string;
  secondaryText?: string;
  intensity?: number;
  group?: string;
}

interface ComboboxProps {
  items: ComboboxItem[];
  value: string;
  onValueChange: (value: string) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  emptyMessage?: string;
  className?: string;
  disabled?: boolean;
  /** Whether clicking the selected item deselects it. Default false. */
  allowDeselect?: boolean;
}

const INTENSITY_CLASSES: Record<number, string> = {
  0: '',
  1: 'bg-green-500/5',
  2: 'bg-green-500/10',
  3: 'bg-green-500/15',
  4: 'bg-green-500/20',
  5: 'bg-green-500/30',
};

function getIntensityClass(intensity?: number): string {
  if (intensity == null || intensity <= 0) return '';
  return INTENSITY_CLASSES[Math.min(intensity, 5)] ?? '';
}

function groupItems(items: ComboboxItem[]): Map<string, ComboboxItem[]> {
  const groups = new Map<string, ComboboxItem[]>();
  for (const item of items) {
    const key = item.group ?? '';
    const group = groups.get(key);
    if (group) {
      group.push(item);
    } else {
      groups.set(key, [item]);
    }
  }
  return groups;
}

export function Combobox({
  items,
  value,
  onValueChange,
  placeholder = 'Select...',
  searchPlaceholder = 'Search...',
  emptyMessage = 'No results found.',
  className,
  disabled = false,
  allowDeselect = false,
}: ComboboxProps) {
  const [open, setOpen] = React.useState(false);

  const selectedItem = items.find((item) => item.value === value);
  const hasGroups = items.some((item) => item.group != null);

  const handleSelect = React.useCallback(
    (itemValue: string) => {
      if (itemValue === value && !allowDeselect) {
        setOpen(false);
        return;
      }
      onValueChange(itemValue === value ? '' : itemValue);
      setOpen(false);
    },
    [onValueChange, value, allowDeselect]
  );

  const renderItem = React.useCallback(
    (item: ComboboxItem) => (
      <Command.Item
        key={item.value}
        value={item.value}
        keywords={[item.label]}
        onSelect={handleSelect}
        className={cn(
          'relative flex cursor-default select-none items-center rounded-sm px-2 py-1.5',
          'text-sm outline-none data-[selected=true]:bg-accent',
          'data-[selected=true]:text-accent-foreground',
          getIntensityClass(item.intensity)
        )}
      >
        <Check
          className={cn(
            'mr-2 h-4 w-4 shrink-0',
            value === item.value ? 'opacity-100' : 'opacity-0'
          )}
        />
        <span className="flex-1 truncate">{item.label}</span>
        {item.secondaryText != null && (
          <span className="ml-auto pl-2 text-sm text-muted-foreground">{item.secondaryText}</span>
        )}
      </Command.Item>
    ),
    [handleSelect, value]
  );

  const renderItems = () => {
    if (!hasGroups) {
      return items.map(renderItem);
    }

    const grouped = groupItems(items);
    return Array.from(grouped.entries()).map(([groupName, groupItems]) =>
      groupName ? (
        <Command.Group key={groupName} heading={groupName}>
          {groupItems.map(renderItem)}
        </Command.Group>
      ) : (
        <React.Fragment key="__ungrouped">{groupItems.map(renderItem)}</React.Fragment>
      )
    );
  };

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="outline"
          role="combobox"
          aria-expanded={open}
          disabled={disabled}
          className={cn('w-full justify-between font-normal', className)}
        >
          <span className="truncate">{selectedItem ? selectedItem.label : placeholder}</span>
          <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
        <Command loop>
          <Command.Input
            placeholder={searchPlaceholder}
            className={cn(
              'flex h-9 w-full rounded-md bg-transparent px-3 py-2 text-sm',
              'outline-none placeholder:text-muted-foreground',
              'disabled:cursor-not-allowed disabled:opacity-50'
            )}
          />
          <Command.List className="max-h-[300px] overflow-y-auto overflow-x-hidden p-1">
            <Command.Empty className="py-6 text-center text-sm text-muted-foreground">
              {emptyMessage}
            </Command.Empty>
            {renderItems()}
          </Command.List>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
