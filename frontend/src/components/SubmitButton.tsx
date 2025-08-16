import { Button, type ButtonProps } from './ui/button';
import { Loader2 } from 'lucide-react';

interface SubmitButtonProps extends ButtonProps {
  isLoading?: boolean;
  disabled?: boolean;
}

export function SubmitButton({
  isLoading = false,
  disabled = false,
  children,
  type = 'submit',
  ...props
}: SubmitButtonProps) {
  return (
    <Button type={type} disabled={disabled || isLoading} {...props}>
      {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
      {children}
    </Button>
  );
}

export default SubmitButton;
