/**
 * ItemFocusView — sidebar drill-in for "looking at" an item worn by
 * another character.
 *
 * Renders the same content body as ``ItemDetailPanel`` (image, name,
 * quality tier badge, markdown description, stats grid, facet chips) but
 * inline rather than inside a Sheet drawer, and without the action
 * buttons row — this is read-only, the looker doesn't own the item.
 *
 * Data is fetched via ``useVisibleItemDetail``; the backend endpoint
 * already enforces the visibility rules (own / same-room / staff bypass)
 * so concealed items return 404 and we render an "unavailable" state.
 */

import { Hand } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { cn } from '@/lib/utils';

import { useVisibleItemDetail } from '../hooks/useVisibleItemDetail';
import type { ItemInstance } from '../types';

interface ItemFocusViewProps {
  item: { id: number; name: string };
  className?: string;
}

export function ItemFocusView({ item, className }: ItemFocusViewProps) {
  const { data, isLoading, isError } = useVisibleItemDetail(item.id);

  if (isLoading) {
    return (
      <div className={cn('flex flex-col gap-4 p-4', className)} data-testid="item-focus-loading">
        <Skeleton className="mx-auto aspect-square w-full max-w-[280px]" />
        <Skeleton className="h-7 w-3/4" />
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-24 w-full" />
      </div>
    );
  }

  if (isError || !data) {
    return (
      <div className={cn('flex flex-col gap-2 p-4', className)}>
        <h2 className="text-xl font-bold">{item.name}</h2>
        <p className="text-sm italic text-muted-foreground">Item details unavailable.</p>
      </div>
    );
  }

  return <ItemFocusBody item={data} className={className} />;
}

interface ItemFocusBodyProps {
  item: ItemInstance;
  className?: string;
}

function ItemFocusBody({ item, className }: ItemFocusBodyProps) {
  const tier = item.quality_tier;
  const tierColor = tier?.color_hex || '';
  const tintedBackground = tierColor ? `${tierColor}20` : undefined;
  const initial = item.display_name.trim().charAt(0).toUpperCase() || '?';
  // The visible-item-detail endpoint uses ``ItemInstanceReadSerializer``,
  // which does not (yet) nest facet labels. Track as a follow-up if Phase A
  // exposes them — until then the chip block is hidden.
  const facetLabels: string[] = [];

  return (
    <div className={cn('flex flex-col', className)}>
      <div className="flex flex-col gap-4 p-4 pb-3">
        <div
          style={tierColor ? { borderLeftColor: tierColor } : undefined}
          className="mx-auto flex aspect-square w-full max-w-[280px] items-center justify-center overflow-hidden rounded-lg border border-l-[3px] bg-muted"
          data-testid="item-focus-image"
        >
          {item.display_image_url ? (
            <img
              src={item.display_image_url}
              alt={item.display_name}
              className="h-full w-full object-cover"
            />
          ) : (
            <span data-fallback-initial className="text-6xl font-bold text-muted-foreground">
              {initial}
            </span>
          )}
        </div>

        <div className="space-y-2">
          <h2 className="text-2xl font-bold">{item.display_name}</h2>
          {tier?.name && (
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                style={tintedBackground ? { backgroundColor: tintedBackground } : undefined}
                className="border-transparent"
              >
                {tier.name}
              </Badge>
            </div>
          )}
        </div>
      </div>

      <Separator />

      <div className="flex flex-col gap-5 p-4">
        {item.display_description && (
          <div
            className={cn('max-w-none text-base leading-relaxed', proseClasses)}
            data-testid="item-focus-description"
          >
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{item.display_description}</ReactMarkdown>
          </div>
        )}

        <StatsGrid item={item} />

        {facetLabels.length > 0 && (
          <div className="flex flex-col gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Facets
            </h4>
            <div className="flex flex-wrap gap-1.5">
              {facetLabels.map((label) => (
                <span
                  key={label}
                  className="rounded-full bg-muted px-2.5 py-0.5 text-xs text-muted-foreground"
                >
                  {label}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

interface StatsGridProps {
  item: ItemInstance;
}

function StatsGrid({ item }: StatsGridProps) {
  const template = item.template;
  return (
    <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
      <Stat label="Weight" value={template?.weight ?? '—'} />
      <Stat label="Size" value={template ? String(template.size) : '—'} />
      <Stat label="Value" value={template ? String(template.value) : '—'} />
      {item.quantity > 1 && <Stat label="Quantity" value={String(item.quantity)} />}
      {item.charges > 0 && <Stat label="Charges" value={String(item.charges)} />}
    </div>
  );
}

interface StatProps {
  label: string;
  value: string;
}

function Stat({ label, value }: StatProps) {
  return (
    <div className="flex items-center justify-between gap-2">
      <span className="flex items-center gap-1.5 text-muted-foreground">
        <Hand className="h-3 w-3 opacity-60" aria-hidden="true" />
        {label}
      </span>
      <span className="font-medium text-foreground">{value}</span>
    </div>
  );
}

/**
 * Manual editorial typography — `@tailwindcss/typography` is not installed.
 * Mirrors the prose classes used by ``ItemDetailPanel``.
 */
const proseClasses = [
  '[&_p]:my-3',
  '[&_p:first-child]:mt-0',
  '[&_p:last-child]:mb-0',
  '[&_strong]:font-semibold',
  '[&_em]:italic',
  '[&_ul]:my-3 [&_ul]:list-disc [&_ul]:pl-5',
  '[&_ol]:my-3 [&_ol]:list-decimal [&_ol]:pl-5',
  '[&_li]:my-1',
  '[&_blockquote]:border-l-2 [&_blockquote]:border-border [&_blockquote]:pl-4 [&_blockquote]:italic [&_blockquote]:text-muted-foreground',
  '[&_code]:rounded [&_code]:bg-muted [&_code]:px-1 [&_code]:py-0.5 [&_code]:text-sm',
  '[&_a]:text-primary [&_a]:underline-offset-2 hover:[&_a]:underline',
].join(' ');
