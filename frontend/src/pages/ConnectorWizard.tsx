import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plug, Plus } from "lucide-react";
import { useState } from "react";
import { listConnectors, registerConnector } from "@/api/client";
import type { ConnectorType, RegisterConnectorRequest } from "@/api/types";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";

const CONNECTOR_FIELDS: Record<
  ConnectorType,
  { key: string; label: string; placeholder: string }[]
> = {
  postgres: [
    { key: "host", label: "Host", placeholder: "localhost" },
    { key: "port", label: "Port", placeholder: "5432" },
    { key: "database", label: "Database", placeholder: "mydb" },
    { key: "user", label: "User", placeholder: "postgres" },
    { key: "password", label: "Password", placeholder: "••••••••" },
    { key: "table", label: "Table", placeholder: "users" },
  ],
  csv: [
    { key: "path", label: "File path", placeholder: "/data/users.csv" },
  ],
  json_api: [
    {
      key: "url",
      label: "API URL",
      placeholder: "https://api.example.com/users",
    },
    {
      key: "headers",
      label: "Headers (JSON)",
      placeholder: '{"Authorization": "Bearer ..."}',
    },
  ],
};

const INITIAL_FORM: RegisterConnectorRequest = {
  name: "",
  type: "postgres",
  config: {},
};

function WizardForm({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<RegisterConnectorRequest>(INITIAL_FORM);

  const { mutate, isPending, error } = useMutation({
    mutationFn: registerConnector,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["connectors"] });
      onDone();
    },
  });

  const fields = CONNECTOR_FIELDS[form.type];

  return (
    <div className="space-y-6">
      {/* Step indicator */}
      <ol className="flex items-center gap-2 text-xs text-slate-500">
        {["Type", "Credentials", "Confirm"].map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span
              className={`flex h-6 w-6 items-center justify-center rounded-full text-xs font-medium ${
                i <= step
                  ? "bg-blue-600 text-white"
                  : "bg-slate-100 text-slate-400"
              }`}
            >
              {i + 1}
            </span>
            <span className={i === step ? "font-medium text-slate-800" : ""}>
              {s}
            </span>
            {i < 2 && <span className="text-slate-300">›</span>}
          </li>
        ))}
      </ol>

      {/* Step 0 — Choose connector type */}
      {step === 0 && (
        <div className="grid grid-cols-3 gap-3">
          {(["postgres", "csv", "json_api"] as ConnectorType[]).map((t) => (
            <button
              key={t}
              onClick={() => {
                setForm((f) => ({ ...f, type: t, config: {} }));
                setStep(1);
              }}
              className={`rounded-lg border-2 p-4 text-sm font-medium transition-colors hover:border-blue-400 ${
                form.type === t
                  ? "border-blue-600 bg-blue-50 text-blue-700"
                  : "border-slate-200"
              }`}
            >
              {t === "postgres"
                ? "PostgreSQL"
                : t === "csv"
                  ? "CSV File"
                  : "JSON API"}
            </button>
          ))}
        </div>
      )}

      {/* Step 1 — Name + credentials */}
      {step === 1 && (
        <div className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">
              Connector name
            </label>
            <input
              className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="e.g. Production CRM"
              value={form.name}
              onChange={(e) =>
                setForm((f) => ({ ...f, name: e.target.value }))
              }
            />
          </div>
          {fields.map(({ key, label, placeholder }) => (
            <div key={key}>
              <label className="mb-1 block text-sm font-medium text-slate-700">
                {label}
              </label>
              <input
                type={key === "password" ? "password" : "text"}
                className="w-full rounded-md border border-slate-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                placeholder={placeholder}
                value={(form.config[key] as string) ?? ""}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    config: { ...f.config, [key]: e.target.value },
                  }))
                }
              />
            </div>
          ))}
          <div className="flex justify-between pt-2">
            <Button variant="ghost" size="sm" onClick={() => setStep(0)}>
              Back
            </Button>
            <Button
              size="sm"
              onClick={() => setStep(2)}
              disabled={!form.name}
            >
              Next
            </Button>
          </div>
        </div>
      )}

      {/* Step 2 — Confirm */}
      {step === 2 && (
        <div className="space-y-4">
          <div className="space-y-2 rounded-lg bg-slate-50 p-4 text-sm">
            <div className="flex justify-between">
              <span className="text-slate-500">Name</span>
              <span className="font-medium text-slate-900">{form.name}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Type</span>
              <span className="font-medium text-slate-900">{form.type}</span>
            </div>
            {Object.entries(form.config)
              .filter(([k]) => k !== "password")
              .map(([k, v]) => (
                <div key={k} className="flex justify-between">
                  <span className="text-slate-500">{k}</span>
                  <span className="max-w-[200px] truncate font-medium text-slate-900">
                    {v}
                  </span>
                </div>
              ))}
          </div>
          {error && (
            <p className="text-sm text-red-600">{(error as Error).message}</p>
          )}
          <div className="flex justify-between pt-2">
            <Button variant="ghost" size="sm" onClick={() => setStep(1)}>
              Back
            </Button>
            <Button size="sm" loading={isPending} onClick={() => mutate(form)}>
              Register
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

export function ConnectorWizard() {
  const [open, setOpen] = useState(false);
  const { data: connectors, isLoading } = useQuery({
    queryKey: ["connectors"],
    queryFn: listConnectors,
  });

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Connectors</h1>
          <p className="mt-1 text-sm text-slate-500">
            Registered data sources
          </p>
        </div>
        <Button onClick={() => setOpen(true)}>
          <Plus size={16} /> New connector
        </Button>
      </div>

      {isLoading ? (
        <p className="text-sm text-slate-400">Loading…</p>
      ) : connectors?.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 text-center">
          <Plug size={40} className="mb-4 text-slate-300" />
          <p className="text-slate-500">No connectors yet.</p>
          <Button className="mt-4" onClick={() => setOpen(true)}>
            Add your first connector
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {connectors?.map((c) => (
            <Card key={c.id}>
              <CardHeader>
                <div className="flex items-start justify-between">
                  <CardTitle className="text-base">{c.name}</CardTitle>
                  <Badge variant="info">{c.type}</Badge>
                </div>
              </CardHeader>
              <CardContent>
                <p className="truncate font-mono text-xs text-slate-400">
                  {c.id}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="New connector"
      >
        <WizardForm onDone={() => setOpen(false)} />
      </Modal>
    </div>
  );
}
