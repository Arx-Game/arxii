/**
 * Stat Modal Component
 *
 * Mobile-only modal for displaying stat descriptions.
 * Opens when a stat card is tapped on mobile devices.
 */

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface StatModalProps {
  stat: { name: string; description: string } | null;
  onClose: () => void;
}

export function StatModal({ stat, onClose }: StatModalProps) {
  const handleOpenChange = (open: boolean) => {
    if (!open) {
      onClose();
    }
  };

  return (
    <Dialog open={stat !== null} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-md">
        {stat && (
          <>
            <DialogHeader>
              <DialogTitle className="capitalize">{stat.name}</DialogTitle>
            </DialogHeader>
            <DialogDescription>{stat.description}</DialogDescription>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
