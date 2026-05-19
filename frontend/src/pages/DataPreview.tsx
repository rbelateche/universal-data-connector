import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { getData } from "@/api/client";
import { Button } from "@/components/ui/Button";

const PAGE_SIZE = 25;

export function DataPreview() {
  const { jobId } = useParams<{ jobId: string }>();
  const navigate = useNavigate();
  const [page, setPage] = useState(0);

  const { data, isLoading, error } = useQuery({
    queryKey: ["data", jobId, page],
    queryFn: () => getData(jobId!, page * PAGE_SIZE, PAGE_SIZE),
    enabled: !!jobId,
  });

  const totalPages = data ? Math.ceil(data.total_rows / PAGE_SIZE) : 0;
  const columns = data?.rows[0] ? Object.keys(data.rows[0]) : [];

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
          <h1 className="text-2xl font-bold text-slate-900">Data Preview</h1>
          {data && (
            <p className="mt-1 text-sm text-slate-500">
              {data.total_rows.toLocaleString()} rows
            </p>
          )}
        </div>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}
      {error && (
        <p className="text-sm text-red-500">{(error as Error).message}</p>
      )}

      {data && (
        <>
          <div className="overflow-auto rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-200 bg-slate-50 text-left">
                  {columns.map((col) => (
                    <th
                      key={col}
                      className="whitespace-nowrap px-4 py-3 font-medium text-slate-500"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {data.rows.map((row, i) => (
                  <tr key={i} className="hover:bg-slate-50">
                    {columns.map((col) => (
                      <td
                        key={col}
                        className="max-w-[200px] truncate px-4 py-2 text-slate-700"
                      >
                        {row[col] == null ? (
                          <span className="text-slate-300">null</span>
                        ) : (
                          String(row[col])
                        )}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {totalPages > 1 && (
            <div className="mt-4 flex items-center justify-between text-sm text-slate-500">
              <span>
                Page {page + 1} of {totalPages}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page === 0}
                  onClick={() => setPage((p) => p - 1)}
                >
                  <ChevronLeft size={14} />
                </Button>
                <Button
                  variant="secondary"
                  size="sm"
                  disabled={page >= totalPages - 1}
                  onClick={() => setPage((p) => p + 1)}
                >
                  <ChevronRight size={14} />
                </Button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
