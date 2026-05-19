import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { getJobMapping, listConnectors, listJobs } from "@/api/client";
import type { ConnectorConfig, Job, MappingResult } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

function ConfidenceCell({ value }: { value: number }) {
  const colorClass =
    value >= 0.8
      ? "text-green-600"
      : value >= 0.5
        ? "text-yellow-600"
        : "text-red-500";
  return (
    <span className={`text-xs font-medium ${colorClass}`}>
      {(value * 100).toFixed(0)}%
    </span>
  );
}

function ConnectorSelect({
  label,
  value,
  connectors,
  onChange,
}: {
  label: string;
  value: string;
  connectors: ConnectorConfig[] | undefined;
  onChange: (v: string) => void;
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium text-slate-700">
        {label} source
      </label>
      <select
        className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        <option value="">Select a connector…</option>
        {connectors?.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
          </option>
        ))}
      </select>
    </div>
  );
}

export function SourceComparison() {
  const { data: connectors } = useQuery({
    queryKey: ["connectors"],
    queryFn: listConnectors,
  });
  const { data: jobs } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
  });

  const [leftId, setLeftId] = useState("");
  const [rightId, setRightId] = useState("");

  function latestDoneJob(connectorId: string): Job | undefined {
    return jobs
      ?.filter(
        (j) =>
          j.connector_id === connectorId &&
          j.status === "done" &&
          j.mapping_id
      )
      .sort(
        (a, b) =>
          new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )[0];
  }

  const leftJob = latestDoneJob(leftId);
  const rightJob = latestDoneJob(rightId);

  const { data: leftMapping } = useQuery({
    queryKey: ["mapping", leftJob?.id],
    queryFn: () => getJobMapping(leftJob!.id),
    enabled: !!leftJob,
  });

  const { data: rightMapping } = useQuery({
    queryKey: ["mapping", rightJob?.id],
    queryFn: () => getJobMapping(rightJob!.id),
    enabled: !!rightJob,
  });

  const allTargets = Array.from(
    new Set([
      ...(leftMapping?.fields.map((f) => f.target_field) ?? []),
      ...(rightMapping?.fields.map((f) => f.target_field) ?? []),
    ])
  ).sort();

  const connectorName = (id: string) =>
    connectors?.find((c: ConnectorConfig) => c.id === id)?.name ?? id;

  const MappingCell = ({
    mapping,
    target,
  }: {
    mapping: MappingResult | undefined;
    target: string;
  }) => {
    const f = mapping?.fields.find((field) => field.target_field === target);
    if (!f) return <span className="text-slate-300">—</span>;
    return (
      <div className="space-y-0.5">
        <div className="font-mono text-slate-700">{f.source_field}</div>
        <ConfidenceCell value={f.confidence} />
      </div>
    );
  };

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-slate-900">
          Source Comparison
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Side-by-side field mapping for two sources
        </p>
      </div>

      <div className="mb-6 grid grid-cols-2 gap-4">
        <ConnectorSelect
          label="Left"
          value={leftId}
          connectors={connectors}
          onChange={setLeftId}
        />
        <ConnectorSelect
          label="Right"
          value={rightId}
          connectors={connectors}
          onChange={setRightId}
        />
      </div>

      {leftId && rightId && (
        <>
          {(!leftJob || !rightJob) && (
            <p className="mb-4 text-sm text-yellow-600">
              {!leftJob &&
                `No completed job for "${connectorName(leftId)}". `}
              {!rightJob &&
                `No completed job for "${connectorName(rightId)}".`}
            </p>
          )}

          {leftMapping && rightMapping && allTargets.length > 0 && (
            <Card>
              <CardHeader>
                <div className="grid grid-cols-2 gap-4">
                  <CardTitle className="text-base">
                    {connectorName(leftId)}
                  </CardTitle>
                  <CardTitle className="text-base">
                    {connectorName(rightId)}
                  </CardTitle>
                </div>
              </CardHeader>
              <CardContent className="p-0">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 bg-slate-50">
                      <th className="w-40 px-4 py-3 text-left font-medium text-slate-500">
                        Target field
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-slate-500">
                        {connectorName(leftId)}
                      </th>
                      <th className="px-4 py-3 text-left font-medium text-slate-500">
                        {connectorName(rightId)}
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {allTargets.map((target) => {
                      const lf = leftMapping.fields.find(
                        (f) => f.target_field === target
                      );
                      const rf = rightMapping.fields.find(
                        (f) => f.target_field === target
                      );
                      const mismatch =
                        lf && rf && lf.source_field !== rf.source_field;
                      return (
                        <tr
                          key={target}
                          className={
                            mismatch ? "bg-yellow-50" : "hover:bg-slate-50"
                          }
                        >
                          <td className="border-b border-slate-100 px-4 py-3">
                            <code className="text-xs text-slate-600">
                              {target}
                            </code>
                            {mismatch && (
                              <Badge variant="warning" className="ml-2">
                                mismatch
                              </Badge>
                            )}
                          </td>
                          <td className="border-b border-slate-100 px-4 py-3 text-sm">
                            <MappingCell
                              mapping={leftMapping}
                              target={target}
                            />
                          </td>
                          <td className="border-b border-slate-100 px-4 py-3 text-sm">
                            <MappingCell
                              mapping={rightMapping}
                              target={target}
                            />
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </CardContent>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
