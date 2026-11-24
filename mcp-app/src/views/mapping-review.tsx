import "@/index.css";

import { Alert, AlertDescription, AlertTitle } from "@alpic-ai/ui/components/alert";
import { Badge } from "@alpic-ai/ui/components/badge";
import { Button } from "@alpic-ai/ui/components/button";
import {
  AlertTriangle,
  Check,
  CircleAlert,
  Maximize2,
  Minimize2,
  ShieldCheck,
  X,
} from "lucide-react";
import { useState } from "react";
import { useDisplayMode, useViewState } from "skybridge/web";
import { useCallTool, useToolInfo } from "@/helpers.js";
import type { ReviewRow } from "@/lib/present.js";
import type { Coverage } from "@/lib/udc-client.js";
import { ConfidenceBadge, errorText, Frame, Loading } from "./components/shared.js";

type CoreField = { path: string; type: string; required: boolean };

type ReviewMeta = {
  core_fields?: CoreField[];
  source_types?: Record<string, string>;
  sample_values?: Record<string, string[]>;
  transformations?: string[];
  threshold?: number;
  "udc/error"?: string;
};

/** Persisted per view instance and visible to the model: the user's decisions only. */
type ReviewState = {
  decisions: Record<string, ReviewRow>;
  coverage: Coverage | null;
  last_action: string | null;
};

type Row = ReviewRow & { unmapped?: boolean };

type Validation = {
  ok: boolean;
  issues: { severity: "error" | "warning"; code: string; field: string; message: string }[];
  dry_run: { rows_tested: number; rows_ok: number };
};

const INLINE_ISSUES = 4;

function unmappedRow(field: string): Row {
  return {
    source_field: field,
    target_field: null,
    confidence: 0,
    transformation: "rename",
    rationale: "The mapper left this field unmapped.",
    status: "proposed",
    state: "dropped",
    unmapped: true,
  };
}

function describeAction(row: ReviewRow): string {
  if (row.state === "rejected") return `rejected ${row.source_field}`;
  return `${row.status} ${row.source_field} → ${row.target_field} (${row.transformation})`;
}

export default function MappingReview() {
  const { input, output, responseMetadata, isPending } = useToolInfo<"propose_mapping">();
  const [state, setState] = useViewState<ReviewState>({
    decisions: {},
    coverage: null,
    last_action: null,
  });
  const [displayMode, setDisplayMode] = useDisplayMode();
  const validate = useCallTool("validate_mapping");
  const [validatedAt, setValidatedAt] = useState<string | null>(null);

  const meta = (responseMetadata ?? {}) as ReviewMeta;

  if (isPending) {
    return (
      <Frame>
        <Loading label={`Loading the ${input?.source_id ?? ""} mapping…`} />
      </Frame>
    );
  }
  if (!output) {
    return (
      <Frame>
        <Alert variant="destructive">
          <CircleAlert />
          <AlertTitle>Could not load this mapping</AlertTitle>
          <AlertDescription>{meta["udc/error"] ?? "The tool returned no data."}</AlertDescription>
        </Alert>
      </Frame>
    );
  }

  // A host can hand back persisted state that predates (or lacks) our keys:
  // persisted state wins over the default, so never assume its shape.
  const decisions = state?.decisions ?? {};
  const rows: Row[] = [
    ...output.mappings.map((r) => decisions[r.source_field] ?? r),
    ...output.unmapped_source_fields.map((f) => decisions[f] ?? unmappedRow(f)),
  ];
  const coverage = state?.coverage ?? output.coverage;
  const pending = rows.filter((r) => r.state === "needs_review");
  const threshold = meta.threshold ?? 0.7;
  const fullscreen = displayMode === "fullscreen";
  const decisionKey = JSON.stringify(decisions);
  const validation =
    validate.data && !validate.data.isError ? (validate.data.structuredContent as Validation) : null;
  const validationError = validate.data ? errorText(validate.data) : null;

  const onDecided = (row: ReviewRow, newCoverage: Coverage) => {
    setState((prev) => ({
      decisions: { ...(prev?.decisions ?? {}), [row.source_field]: row },
      coverage: newCoverage,
      last_action: describeAction(row),
    }));
  };

  const runValidation = () => {
    setValidatedAt(decisionKey);
    validate.callTool({ source_id: output.source_id });
  };

  const narration =
    `Reviewing the ${output.source_name} mapping: ` +
    (pending.length
      ? `${pending.length} proposal(s) await the user's decision (${pending
          .map((r) => r.source_field)
          .join(", ")})`
      : "no proposal awaits a decision") +
    `; ${coverage.required_mapped}/${coverage.required_total} required fields mapped` +
    (state?.last_action ? `; last action in the table: ${state.last_action}` : "");

  return (
    <Frame dataLlm={narration}>
      <header className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="flex min-w-0 flex-col gap-1.5">
          <h2 className="text-base font-semibold">
            {output.source_name}
            <span className="font-normal text-muted-foreground"> → Product</span>
          </h2>
          <CoverageSummary coverage={coverage} />
          <p className="text-xs text-muted-foreground">
            {pending.length
              ? `${pending.length} proposal${pending.length > 1 ? "s" : ""} below ${Math.round(
                  threshold * 100,
                )}% confidence ${pending.length > 1 ? "need" : "needs"} your decision.`
              : "Every proposal is decided or above the confidence threshold."}
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <Button
            variant="cta"
            loading={validate.isPending}
            icon={<ShieldCheck />}
            onClick={runValidation}
          >
            Validate
          </Button>
          <Button
            variant="secondary"
            size="icon"
            aria-label={fullscreen ? "Collapse" : "Expand"}
            onClick={() => setDisplayMode(fullscreen ? "inline" : "fullscreen")}
          >
            {fullscreen ? <Minimize2 /> : <Maximize2 />}
          </Button>
        </div>
      </header>

      <table className="w-full table-fixed border-collapse text-left">
        <thead>
          <tr className="border-b border-border text-xs text-muted-foreground">
            <th className="w-[34%] py-2 pr-2 font-medium">Source field</th>
            <th className="w-[34%] py-2 pr-2 font-medium">Core field · transformation</th>
            <th className="w-[14%] py-2 pr-2 font-medium">Confidence</th>
            <th className="w-[18%] py-2 text-right font-medium">Decision</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <MappingRowView
              key={row.source_field}
              row={row}
              sourceId={output.source_id}
              meta={meta}
              threshold={threshold}
              fullscreen={fullscreen}
              onDecided={onDecided}
            />
          ))}
        </tbody>
      </table>

      {validationError && (
        <Alert variant="destructive" className="mt-3">
          <CircleAlert />
          <AlertTitle>Validation failed to run</AlertTitle>
          <AlertDescription>{validationError}</AlertDescription>
        </Alert>
      )}
      {validation && (
        <ValidationPanel
          validation={validation}
          stale={validatedAt !== decisionKey}
          fullscreen={fullscreen}
        />
      )}
    </Frame>
  );
}

function CoverageSummary({ coverage }: { coverage: Coverage }) {
  const ratio = coverage.required_total ? coverage.required_mapped / coverage.required_total : 0;
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs">
      <div className="flex items-center gap-2">
        <div className="h-1.5 w-24 overflow-hidden rounded-full bg-muted">
          <div
            className={`h-full rounded-full ${ratio === 1 ? "bg-success" : "bg-foreground/60"}`}
            style={{ width: `${Math.round(ratio * 100)}%` }}
          />
        </div>
        <span className="font-medium tabular-nums">
          {coverage.required_mapped}/{coverage.required_total} required fields mapped
        </span>
      </div>
      {coverage.pending_required.map((f) => (
        <Badge key={f} variant="warning" size="sm" title="Only a low-confidence proposal maps here">
          {f}: review
        </Badge>
      ))}
      {coverage.missing_required.map((f) => (
        <Badge key={f} variant="error" size="sm" title="No field of this source maps here">
          {f}: missing
        </Badge>
      ))}
    </div>
  );
}

function MappingRowView({
  row,
  sourceId,
  meta,
  threshold,
  fullscreen,
  onDecided,
}: {
  row: Row;
  sourceId: string;
  meta: ReviewMeta;
  threshold: number;
  fullscreen: boolean;
  onDecided: (row: ReviewRow, coverage: Coverage) => void;
}) {
  const { callTool, isPending } = useCallTool("update_mapping");
  const [error, setError] = useState<string | null>(null);

  const decide = (decision: {
    status: "accepted" | "rejected" | "edited";
    target_field?: string;
    transformation?: (typeof row)["transformation"];
  }) => {
    setError(null);
    callTool(
      {
        source_id: sourceId,
        source_field: row.source_field,
        ...decision,
      } as Parameters<typeof callTool>[0],
      {
        onSuccess: (result) => {
          const message = errorText(result);
          if (message) {
            setError(message);
            return;
          }
          const sc = result.structuredContent as { mapping: ReviewRow; coverage: Coverage };
          onDecided(sc.mapping, sc.coverage);
        },
        onError: () => setError("Could not reach the app. Try again."),
      },
    );
  };

  const needsReview = row.state === "needs_review";
  // The mapper proposes to leave this column out; accepting confirms that.
  const isDrop = row.transformation === "drop";
  const inactive = row.state === "rejected" || row.state === "dropped";
  const samples = meta.sample_values?.[row.source_field] ?? [];
  const declaredType = meta.source_types?.[row.source_field];
  const coreFields = meta.core_fields ?? [];
  const transformations = (meta.transformations ?? []).filter((t) => t !== "drop");

  return (
    <>
      <tr
        className={`border-b border-border align-top ${
          needsReview ? "bg-warning/10" : ""
        } ${inactive ? "text-muted-foreground" : ""}`}
      >
        <td className="py-2 pr-2">
          <div className="truncate font-mono text-xs font-semibold" title={row.source_field}>
            {row.source_field}
          </div>
          <div className="truncate text-[11px] text-muted-foreground">
            {[declaredType, samples.length ? `e.g. ${samples.join(" · ")}` : null]
              .filter(Boolean)
              .join(" — ")}
          </div>
          <div
            className={`mt-0.5 text-[11px] text-muted-foreground ${fullscreen ? "" : "line-clamp-2"}`}
            title={row.rationale}
          >
            {row.rationale}
          </div>
        </td>
        <td className="py-2 pr-2">
          <select
            aria-label={`Core field for ${row.source_field}`}
            className="w-full rounded-md border border-border bg-background px-1.5 py-1 text-xs"
            value={inactive ? "" : (row.target_field ?? "")}
            disabled={isPending}
            onChange={(e) =>
              e.target.value
                ? decide({ status: "edited", target_field: e.target.value })
                : decide({ status: "rejected" })
            }
          >
            <option value="">— not mapped —</option>
            {coreFields.map((f) => (
              <option key={f.path} value={f.path}>
                {f.path}
                {f.required ? " *" : ""}
              </option>
            ))}
          </select>
          {isDrop && !inactive && (
            <div className="mt-1 text-[11px] italic text-muted-foreground">
              proposed: leave unmapped
            </div>
          )}
          {!inactive && !isDrop && (
            <select
              aria-label={`Transformation for ${row.source_field}`}
              className="mt-1 w-full rounded-md border border-border bg-background px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground"
              value={row.transformation}
              disabled={isPending}
              onChange={(e) =>
                decide({
                  status: "edited",
                  transformation: e.target.value as (typeof row)["transformation"],
                })
              }
              title={
                row.value_map
                  ? Object.entries(row.value_map)
                      .map(([k, v]) => `${k} → ${String(v)}`)
                      .join(", ")
                  : undefined
              }
            >
              {transformations.map((t) => (
                <option key={t} value={t}>
                  via {t}
                </option>
              ))}
            </select>
          )}
        </td>
        <td className="py-2 pr-2">
          {row.unmapped ? (
            <span className="text-[11px]">—</span>
          ) : row.status === "proposed" ? (
            <ConfidenceBadge value={row.confidence} threshold={threshold} />
          ) : (
            <Badge
              variant={row.state === "rejected" ? "secondary" : "success"}
              size="sm"
              title={`Decided by a reviewer; mapper confidence was ${Math.round(row.confidence * 100)}%`}
            >
              {row.status === "accepted"
                ? isDrop
                  ? "✓ left out"
                  : "✓ accepted"
                : row.status === "edited"
                  ? "✎ edited"
                  : "✕ rejected"}
            </Badge>
          )}
        </td>
        <td className="py-2 text-right">
          <div className="inline-flex gap-1">
            <Button
              variant={needsReview ? "primary" : "secondary"}
              size="icon"
              aria-label={`Accept ${row.source_field}`}
              title={isDrop ? "Keep it unmapped" : "Accept"}
              disabled={isPending || row.unmapped || row.state === "dropped" || row.status === "accepted"}
              onClick={() => decide({ status: "accepted" })}
            >
              <Check />
            </Button>
            <Button
              variant="secondary"
              size="icon"
              aria-label={`Reject ${row.source_field}`}
              title="Reject"
              disabled={isPending || row.unmapped || isDrop || row.state === "rejected"}
              onClick={() => decide({ status: "rejected" })}
            >
              <X />
            </Button>
          </div>
          {row.status !== "proposed" && (
            <div className="mt-1 text-[10px] text-muted-foreground">saved</div>
          )}
        </td>
      </tr>
      {error && (
        <tr>
          <td colSpan={4} className="pb-2 text-xs text-destructive">
            {row.source_field}: {error}
          </td>
        </tr>
      )}
    </>
  );
}

function ValidationPanel({
  validation,
  stale,
  fullscreen,
}: {
  validation: Validation;
  stale: boolean;
  fullscreen: boolean;
}) {
  const errors = validation.issues.filter((i) => i.severity === "error");
  const shown = fullscreen ? validation.issues : validation.issues.slice(0, INLINE_ISSUES);
  const hidden = validation.issues.length - shown.length;
  const dry = `${validation.dry_run.rows_ok}/${validation.dry_run.rows_tested} sample rows transformed cleanly`;

  return (
    <Alert variant={validation.ok ? "success" : "warning"} className="mt-3">
      {validation.ok ? <ShieldCheck /> : <AlertTriangle />}
      <AlertTitle>
        {validation.ok
          ? "Ready to export"
          : `${errors.length} issue${errors.length > 1 ? "s block" : " blocks"} export`}
        {stale && <span className="font-normal text-muted-foreground"> · out of date, validate again</span>}
      </AlertTitle>
      <AlertDescription>
        <p className="mb-1">{dry}.</p>
        <ul className="flex flex-col gap-1">
          {shown.map((issue) => (
            <li key={`${issue.code}-${issue.field}`} className="flex gap-2 text-xs">
              <Badge variant={issue.severity === "error" ? "error" : "warning"} size="sm">
                {issue.code}
              </Badge>
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
        {hidden > 0 && (
          <p className="mt-1 text-xs text-muted-foreground">
            {hidden} more — expand to see all, or ask in the chat.
          </p>
        )}
      </AlertDescription>
    </Alert>
  );
}
