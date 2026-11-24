import "@/index.css";

import { Alert, AlertDescription, AlertTitle } from "@alpic-ai/ui/components/alert";
import { Button } from "@alpic-ai/ui/components/button";
import { StatusDot } from "@alpic-ai/ui/components/status-dot";
import { CircleAlert, MessageSquareText } from "lucide-react";
import { useSendFollowUpMessage } from "skybridge/web";
import { useToolInfo } from "@/helpers.js";
import { Frame, Loading, percent } from "./components/shared.js";

type Cell = {
  field: string;
  source_id: string;
  status: "mapped" | "needs_review" | "missing";
  source_col: string | null;
  confidence: number | null;
};

const DOT = { mapped: "success", needs_review: "warning", missing: "muted" } as const;
const LABEL = { mapped: "mapped", needs_review: "needs review", missing: "missing" } as const;

export default function CoverageMatrix() {
  const { output, responseMetadata, isPending } = useToolInfo<"get_coverage">();
  const sendFollowUp = useSendFollowUpMessage();
  const meta = (responseMetadata ?? {}) as { cells?: Cell[]; "udc/error"?: string };

  if (isPending) {
    return (
      <Frame>
        <Loading label="Comparing sources…" />
      </Frame>
    );
  }
  if (!output) {
    return (
      <Frame>
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>Could not load the coverage</AlertTitle>
          <AlertDescription>{meta["udc/error"] ?? "The tool returned no data."}</AlertDescription>
        </Alert>
      </Frame>
    );
  }

  const cellOf = (field: string, sourceId: string) =>
    meta.cells?.find((c) => c.field === field && c.source_id === sourceId);
  const fields = [...output.fields].sort((a, b) => Number(b.required) - Number(a.required));
  const singleSource = output.fields
    .filter((f) => f.required)
    .flatMap((f) => {
      const from = Object.entries(f.by_source).filter(([, s]) => s === "mapped");
      return from.length === 1 ? [`${f.field} only from ${from[0][0]}`] : [];
    });
  const narration =
    `Coverage of the Product core model across ${output.sources.length} sources. ` +
    (output.unsourced_required.length
      ? `No source maps: ${output.unsourced_required.join(", ")}. `
      : "Every required field has at least one source. ") +
    (singleSource.length ? `Single source: ${singleSource.join("; ")}.` : "");

  return (
    <Frame dataLlm={narration}>
      <h2 className="mb-1 text-base font-semibold">Product coverage by source</h2>
      <p className="mb-3 text-xs text-muted-foreground">
        Which core fields each source can fill. * marks required fields.
      </p>

      <table className="w-full table-fixed border-collapse text-left">
        <thead>
          <tr className="border-b border-border align-bottom">
            <th className="w-[28%] py-2 pr-2 text-xs font-medium text-muted-foreground">
              Core field
            </th>
            {output.sources.map((s) => (
              <th key={s.source_id} className="py-2 pr-2 align-bottom">
                <div className="truncate text-xs font-semibold" title={s.name}>
                  {s.source_id}
                </div>
                <div className="text-[11px] font-normal text-muted-foreground tabular-nums">
                  {s.required_mapped}/{s.required_total} required
                </div>
                <Button
                  variant="link"
                  className="h-auto p-0 text-[11px]"
                  icon={<MessageSquareText />}
                  onClick={() =>
                    sendFollowUp(`Open the mapping review for the ${s.source_id} source.`)
                  }
                >
                  Review
                </Button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => (
            <tr key={f.field} className="border-b border-border">
              <td className="py-1.5 pr-2 font-mono text-xs">
                {f.field}
                {f.required && <span className="text-destructive"> *</span>}
              </td>
              {output.sources.map((s) => {
                const status = f.by_source[s.source_id] ?? "missing";
                const cell = cellOf(f.field, s.source_id);
                const missingRequired = status === "missing" && f.required;
                return (
                  <td
                    key={s.source_id}
                    className={`py-1.5 pr-2 ${missingRequired ? "bg-destructive/5" : ""}`}
                    title={
                      cell?.source_col
                        ? `${cell.source_col}${cell.confidence !== null ? ` · ${percent(cell.confidence)}` : ""}`
                        : LABEL[status]
                    }
                  >
                    <div className="flex items-center gap-1.5 text-xs">
                      <StatusDot variant={DOT[status]} />
                      <span
                        className={`truncate ${status === "missing" ? "text-muted-foreground" : "font-mono"}`}
                      >
                        {cell?.source_col ?? LABEL[status]}
                      </span>
                    </div>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
        {(["mapped", "needs_review", "missing"] as const).map((s) => (
          <span key={s} className="inline-flex items-center gap-1.5">
            <StatusDot variant={DOT[s]} /> {LABEL[s]}
          </span>
        ))}
      </div>

      {output.unsourced_required.length > 0 && (
        <Alert variant="warning" className="mt-3">
          <CircleAlert />
          <AlertTitle>No source maps these required fields yet</AlertTitle>
          <AlertDescription>{output.unsourced_required.join(", ")}</AlertDescription>
        </Alert>
      )}
    </Frame>
  );
}
