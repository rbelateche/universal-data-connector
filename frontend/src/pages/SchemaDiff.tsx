import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Minus, Plus } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";
import { getSchemaDiff } from "@/api/client";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";

export function SchemaDiff() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();

  const {
    data: diff,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["diff", jobId],
    queryFn: () => getSchemaDiff(jobId!),
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
          <h1 className="text-2xl font-bold text-slate-900">Schema Diff</h1>
          <p className="mt-1 text-sm text-slate-500">
            Changes vs. previous run
          </p>
        </div>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && (
        <p className="text-sm text-red-500">{(error as Error).message}</p>
      )}

      {diff && !diff.has_changes && (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Badge variant="success" className="mb-3 text-sm">
            No changes
          </Badge>
          <p className="text-slate-500">
            Schema is identical to the previous run.
          </p>
        </div>
      )}

      {diff?.has_changes && (
        <div className="space-y-4">
          {diff.added.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-green-700">
                  <Plus size={16} /> Added fields ({diff.added.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {diff.added.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm">
                      <Plus size={14} className="text-green-500" />
                      <code className="rounded bg-green-50 px-1.5 py-0.5 text-green-700">
                        {f}
                      </code>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {diff.removed.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-red-700">
                  <Minus size={16} /> Removed fields ({diff.removed.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-1">
                  {diff.removed.map((f) => (
                    <li key={f} className="flex items-center gap-2 text-sm">
                      <Minus size={14} className="text-red-500" />
                      <code className="rounded bg-red-50 px-1.5 py-0.5 text-red-700">
                        {f}
                      </code>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}

          {diff.changed.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-yellow-700">
                  Changed fields ({diff.changed.length})
                </CardTitle>
              </CardHeader>
              <CardContent>
                <ul className="space-y-2">
                  {diff.changed.map(({ field, before, after }) => (
                    <li
                      key={field}
                      className="flex items-center gap-3 text-sm"
                    >
                      <code className="font-medium text-slate-700">
                        {field}
                      </code>
                      <code className="rounded bg-red-50 px-1.5 py-0.5 text-red-600 line-through">
                        {before}
                      </code>
                      <ArrowRight size={12} className="text-slate-400" />
                      <code className="rounded bg-green-50 px-1.5 py-0.5 text-green-600">
                        {after}
                      </code>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          )}
        </div>
      )}
    </div>
  );
}
