import { Badge } from "@alpic-ai/ui/components/badge";
import type { ReactNode } from "react";
import { useUser } from "skybridge/web";

/** Applies the host theme (light / dark) and base typography. */
export function Frame({ children, dataLlm }: { children: ReactNode; dataLlm?: string }) {
  const { theme } = useUser();
  return (
    <div className={theme === "dark" ? "dark" : ""}>
      <div
        data-llm={dataLlm}
        className="w-full bg-background p-4 font-sans text-sm text-foreground"
      >
        {children}
      </div>
    </div>
  );
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Mapper confidence: green ≥ 90%, neutral ≥ threshold, amber below it. */
export function ConfidenceBadge({ value, threshold }: { value: number; threshold: number }) {
  const variant = value >= 0.9 ? "success" : value >= threshold ? "secondary" : "warning";
  return (
    <Badge variant={variant} size="sm" className="tabular-nums">
      {percent(value)}
    </Badge>
  );
}

/** The message of a failed tool call, from a view-side call or the view's own tool. */
export function errorText(result: {
  isError?: boolean;
  content?: { type: string; text?: string }[];
  meta?: Record<string, unknown>;
}): string | null {
  if (!result.isError) return null;
  const fromMeta = result.meta?.["udc/error"];
  if (typeof fromMeta === "string") return fromMeta;
  const text = result.content?.find((c) => c.type === "text")?.text;
  return text ?? "The action failed. Try again.";
}

export function Loading({ label }: { label: string }) {
  return (
    <div className="flex flex-col gap-3" aria-busy="true">
      <p className="text-muted-foreground">{label}</p>
      {[0, 1, 2, 3].map((i) => (
        <div key={i} className="h-9 animate-pulse rounded-md bg-muted" />
      ))}
    </div>
  );
}
