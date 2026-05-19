import { clsx } from "clsx";
import type { ReactNode } from "react";

type Variant = "default" | "success" | "warning" | "error" | "info" | "muted";

const variantClasses: Record<Variant, string> = {
  default: "bg-slate-100 text-slate-700",
  success: "bg-green-100 text-green-700",
  warning: "bg-yellow-100 text-yellow-700",
  error: "bg-red-100 text-red-700",
  info: "bg-blue-100 text-blue-700",
  muted: "bg-gray-100 text-gray-500",
};

interface BadgeProps {
  variant?: Variant;
  children: ReactNode;
  className?: string;
  pulse?: boolean;
}

export function Badge({
  variant = "default",
  children,
  className,
  pulse,
}: BadgeProps) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
        variantClasses[variant],
        className
      )}
    >
      {pulse && (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-current" />
        </span>
      )}
      {children}
    </span>
  );
}
