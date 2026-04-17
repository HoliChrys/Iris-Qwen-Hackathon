import { useAtomValue } from 'jotai';
import { pipelineStepsAtom } from '@/stores';

export function PipelineStatus() {
  const steps = useAtomValue(pipelineStepsAtom);
  const allPending = steps.every((s) => s.status === 'pending');
  if (allPending) return null;

  return (
    <div className="bg-card border border-border rounded-xl p-3.5 mt-2">
      {steps.map((step) => (
        <div key={step.name} className="flex items-center gap-2 py-1">
          <div
            className={`w-2 h-2 rounded-full ${
              step.status === 'done' ? 'bg-sb5-green' :
              step.status === 'active' ? 'bg-sb5-amber animate-pulse-dot' :
              step.status === 'error' ? 'bg-sb5-red' :
              'bg-muted'
            }`}
          />
          <span className={`text-xs ${
            step.status === 'active' ? 'text-foreground font-medium' : 'text-muted-foreground'
          }`}>
            {step.label}
            {step.detail && <span className="text-muted-foreground"> — {step.detail}</span>}
          </span>
          {step.duration_ms != null && (
            <span className="ml-auto text-[10px] text-muted-foreground">
              {step.duration_ms < 1000 ? `${step.duration_ms}ms` : `${(step.duration_ms / 1000).toFixed(1)}s`}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}
