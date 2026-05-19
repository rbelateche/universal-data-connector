import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Play, RefreshCw } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { listConnectors, listJobs, triggerJob } from "@/api/client";
import type { JobStatus, TriggerJobRequest } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { ProgressBar } from "@/components/ui/ProgressBar";

const STATUS_VARIANT: Record<
  JobStatus,
  "muted" | "info" | "success" | "error"
> = {
  pending: "muted",
  running: "info",
  done: "success",
  failed: "error",
};

const CANONICAL_SCHEMAS = ["contact", "order", "product"];

function formatDate(s: string | null) {
  if (!s) return "—";
  return new Date(s).toLocaleString();
}

function TriggerModal({ onClose }: { onClose: () => void }) {
  const qc = useQueryClient();
  const { data: connectors } = useQuery({
    queryKey: ["connectors"],
    queryFn: listConnectors,
  });
  const [form, setForm] = useState<TriggerJobRequest>({
    connector_id: "",
    target_schema: "contact",
  });

  const { mutate, isPending, error } = useMutation({
    mutationFn: triggerJob,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      onClose();
    },
  });

  return (
    <div className="space-y-4">
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Connector
        </label>
        <select
          className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={form.connector_id}
          onChange={(e) =>
            setForm((f) => ({ ...f, connector_id: e.target.value }))
          }
        >
          <option value="">Select a connector…</option>
          {connectors?.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">
          Target schema
        </label>
        <select
          className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
          value={form.target_schema}
          onChange={(e) =>
            setForm((f) => ({ ...f, target_schema: e.target.value }))
          }
        >
          {CANONICAL_SCHEMAS.map((s) => (
            <option key={s} value={s}>
              {s.charAt(0).toUpperCase() + s.slice(1)}
            </option>
          ))}
        </select>
      </div>
      {error && (
        <p className="text-sm text-red-600">{(error as Error).message}</p>
      )}
      <div className="flex justify-end gap-3 pt-2">
        <Button variant="secondary" onClick={onClose}>
          Cancel
        </Button>
        <Button
          loading={isPending}
          disabled={!form.connector_id}
          onClick={() => mutate(form)}
        >
          <Play size={14} /> Run job
        </Button>
      </div>
    </div>
  );
}

export function JobDashboard() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const {
    data: jobs,
    isLoading,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["jobs"],
    queryFn: listJobs,
    refetchInterval: 3000,
  });

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Jobs</h1>
          <p className="mt-1 text-sm text-slate-500">
            Ingestion + mapping runs
          </p>
        </div>
        <div className="flex gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => void refetch()}
            loading={isFetching}
          >
            <RefreshCw size={14} />
          </Button>
          <Button onClick={() => setOpen(true)}>
            <Play size={14} /> New job
          </Button>
        </div>
      </div>

      {isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : jobs?.length === 0 ? (
        <p className="text-sm text-slate-400">No jobs yet.</p>
      ) : (
        <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-left">
                <th className="px-4 py-3 font-medium text-slate-500">ID</th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Schema
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Status
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Progress
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Created
                </th>
                <th className="px-4 py-3 font-medium text-slate-500">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {jobs?.map((job) => (
                <tr key={job.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-mono text-xs text-slate-400">
                    {job.id.slice(0, 8)}…
                  </td>
                  <td className="px-4 py-3 font-medium capitalize text-slate-900">
                    {job.target_schema}
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      variant={STATUS_VARIANT[job.status]}
                      pulse={job.status === "running"}
                    >
                      {job.status}
                    </Badge>
                  </td>
                  <td className="w-36 px-4 py-3">
                    <div className="flex items-center gap-2">
                      <ProgressBar
                        value={job.progress_pct}
                        className="flex-1"
                        color={job.status === "done" ? "green" : "blue"}
                      />
                      <span className="w-8 text-right text-xs text-slate-400">
                        {job.progress_pct}%
                      </span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-slate-500">
                    {formatDate(job.created_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-1">
                      {job.mapping_id && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() =>
                            navigate(`/jobs/${job.id}/mapping`)
                          }
                        >
                          Mapping
                        </Button>
                      )}
                      {job.status === "done" && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              navigate(`/jobs/${job.id}/data`)
                            }
                          >
                            Data
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() =>
                              navigate(`/jobs/${job.id}/diff`)
                            }
                          >
                            Diff
                          </Button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New ingestion job"
      >
        <TriggerModal onClose={() => setOpen(false)} />
      </Modal>
    </div>
  );
}
