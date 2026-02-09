import { useCallback, useState } from 'react';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { dismissRoulette, requestSkip } from '@/store/rouletteSlice';
import { RouletteWheel } from './RouletteWheel';
import { RouletteResult } from './RouletteResult';

export function RouletteModal() {
  const dispatch = useAppDispatch();
  const current = useAppSelector((state) => state.roulette.current);
  const skipRequested = useAppSelector((state) => state.roulette.skipRequested);
  const [animationDone, setAnimationDone] = useState(false);

  const handleAnimationComplete = useCallback(() => {
    setAnimationDone(true);
  }, []);

  const handleDismiss = useCallback(() => {
    setAnimationDone(false);
    dispatch(dismissRoulette());
  }, [dispatch]);

  const handleClick = useCallback(() => {
    if (!animationDone) {
      dispatch(requestSkip());
    }
  }, [animationDone, dispatch]);

  if (!current) return null;

  const selected = current.consequences.find((c) => c.is_selected);

  return (
    <Dialog
      open={!!current}
      onOpenChange={(open) => {
        if (!open && animationDone) {
          handleDismiss();
        }
      }}
    >
      <DialogContent
        className="max-w-md"
        onClick={handleClick}
        onPointerDownOutside={(e) => {
          // Prevent closing during animation
          if (!animationDone) {
            e.preventDefault();
          }
        }}
        onEscapeKeyDown={(e) => {
          if (!animationDone) {
            e.preventDefault();
            dispatch(requestSkip());
          }
        }}
      >
        <DialogHeader>
          <DialogTitle className="text-center">{current.template_name}</DialogTitle>
        </DialogHeader>

        <div className="flex flex-col items-center gap-4 py-4">
          <RouletteWheel
            consequences={current.consequences}
            onAnimationComplete={handleAnimationComplete}
            skipRequested={skipRequested}
          />

          {animationDone && selected && <RouletteResult consequence={selected} />}
        </div>

        {!animationDone && (
          <p className="text-center text-xs text-muted-foreground">Click to skip</p>
        )}
      </DialogContent>
    </Dialog>
  );
}
