import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, Edit2, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getJobMapping, overrideField } from "@/api/client";
import type { FieldMapping } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Tooltip } from "@/components/ui/Tooltip";

const TRANSFORMS = [
  "passthrough",
  "to_string",
  "to_int",
  "to_float",
  "to_bool",
  "to_date",
] as const;

function ConfidenceBar({ value }: { value: number }) {
  const color =
    value >= 0.8
      ? "bg-green-500"
      : value >= 0.5
        ? "bg-yellow-500"
        : "bg-red-400";
  return (
    <div className="flex items-center gap-2">
      <div className="h-1.5 w-24 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${value * 100}%` }}
        />
      </div>
      <span className="text-xs text-slate-400">
        {(value * 100).toFixed(0)}%
      </span>
    </div>
  );
}

function FieldRow({
  jobId,
  field,
}: {
  jobId: string;
  field: FieldMapping;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [targetField, setTargetField] = useState(field.target_field);
  const [transform, setTransform] = useState(field.transform);

  const { mutate, isPending } = useMutation({
    mutationFn: () =>
      overrideField(jobId, field.source_field, {
        target_field: targetField,
        transform,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["mapping", jobId] });
      setEditing(false);
    },
  });

  const reasoningPreview =
    field.reasoning.length > 50
      ? field.reasoning.slice(0, 50) + "…"
      : field.reasoning;

  return (
    <tr className="border-b border-slate-100 hover:bg-slate-50">
      <td className="px-4 py-3 font-mono text-sm text-slate-700">
        {field.source_field}
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <input
            className="w-full rounded border border-slate-200 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            value={targetField}
            onChange={(e) => setTargetField(e.target.value)}
          />
        ) : (
          <span className="font-medium text-slate-900">
            {field.target_field}
          </span>
        )}
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <select
            className="rounded border border-slate-200 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-500"
            value={transform}
            onChange={(e) => setTransform(e.target.value)}
          >
            {TRANSFORMS.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        ) : (
          <code className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
            {field.transform}
          </code>
        )}
      </td>
      <td className="px-4 py-3">
        <ConfidenceBar value={field.confidence} />
      </td>
      <td className="px-4 py-3">
        <Tooltip content={field.reasoning}>
          <span className="block max-w-[180px] cursor-help truncate text-xs text-slate-500 underline decoration-dotted">
            {reasoningPreview}
          </span>
        </Tooltip>
      </td>
      <td className="px-4 py-3">
        {field.overridden && <Badge variant="warning">overridden</Badge>}
      </td>
      <td className="px-4 py-3">
        {editing ? (
          <div className="flex gap-1">
            <Button
              size="sm"
              loading={isPending}
              onClick={() => mutate()}
            >
              <Check size={12} />
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setEditing(false)}
            >
              <X size={12} />
            </Button>
          </div>
        ) : (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setEditing(true)}
          >
            <Edit2 size={12} /> Edit
          </Button>
        )}
      </td>
    </tr>
  );
}

export function MappingInspector() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const {
    data: mapping,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["mapping", jobId],
    queryFn: () => getJobMapping(jobId!),
    enabled: !!jobId,
  });

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => navigate("/jobs")}
        >
          <ArrowLeft size={14} /> Back
        </Button>
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Field Mapping
          </h1>
          {mapping && (
            <p className="mt-1 text-sm text-slate-500">
              {mapping.source_schema} →{" "}
              <span className="capitalize">{mapping.target_schema}</span> ·
              v{mapping.version}
            </p>
          )}
        </div>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && (
        <p className="text-sm text-red-500">{(error as Error).message}</p>
      )}

      {mapping && (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left">
                <th className="px-4 py-3 font-medium text-slate-500">
                  Source field
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Target field
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Transform
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Confidence
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Reasoning
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-slate-500" />
              </tr>
            </thead>
            <tbody>
              {mapping.fields.map((field) => (
                <FieldRow
                  key={field.source_field}
                  jobId={jobId!}
                  field={field}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
