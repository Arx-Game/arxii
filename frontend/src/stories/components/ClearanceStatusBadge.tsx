/**
 * CustodyClearance status pill badge (#2001 Task 8).
 * PENDING=amber, GRANTED=green, DENIED=red, ESCALATED=purple.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';
import type { CustodyClearanceStatus } from '../types';

const STATUS_LABELS: Record<CustodyClearanceStatus, string> = {
  pending: 'Pending',
  granted: 'Granted',
  denied: 'Denied',
  escalated: 'Escalated',
};

const STATUS_CLASSES: Record<CustodyClearanceStatus, string> = {
  pending: 'bg-amber-600 text-white border-transparent',
  granted: 'bg-green-600 text-white border-transparent',
  denied: 'bg-red-600 text-white border-transparent',
  escalated: 'bg-purple-600 text-white border-transparent',
};

interface ClearanceStatusBadgeProps {
  status: CustodyClearanceStatus;
  className?: string;
}

export function ClearanceStatusBadge({ status, className }: ClearanceStatusBadgeProps) {
  return <Badge className={cn(STATUS_CLASSES[status], className)}>{STATUS_LABELS[status]}</Badge>;
}
