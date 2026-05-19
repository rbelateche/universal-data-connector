import { clsx } from "clsx";

interface ProgressBarProps {
  value: number; // 0–100
  className?: string;
  color?: "blue" | "green";
}

export function ProgressBar({
  value,
  className,
  color = "blue",
}: ProgressBarProps) {
  const colorClass = color === "green" ? "bg-green-500" : "bg-blue-500";
  return (
    <div
      className={clsx(
        "h-2 w-full overflow-hidden rounded-full bg-slate-100",
        className
      )}
    >
      <div
        className={clsx(
          "h-full rounded-full transition-all duration-500",
          colorClass
        )}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}
