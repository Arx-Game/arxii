import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import { useRestMutation } from '../fatigueQueries';

interface RestButtonProps {
  restedToday: boolean;
  disabled?: boolean;
  className?: string;
}

export function RestButton({ restedToday, disabled, className }: RestButtonProps) {
  const restMutation = useRestMutation();

  function handleRest() {
    restMutation.mutate(undefined, {
      onSuccess: (data) => {
        toast.success(data.detail || 'You have rested successfully.');
      },
      onError: (error: Error) => {
        toast.error(error.message || 'Failed to rest.');
      },
    });
  }

  const isDisabled = restedToday || disabled || restMutation.isPending;

  return (
    <Button
      variant={restedToday ? 'secondary' : 'default'}
      size="sm"
      className={className}
      disabled={isDisabled}
      onClick={handleRest}
    >
      {restedToday ? 'Already Rested' : 'Rest'}
      <span className="ml-1 text-xs opacity-70">10 AP</span>
    </Button>
  );
}
