import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { ConnectorWizard } from "@/pages/ConnectorWizard";
import { DataPreview } from "@/pages/DataPreview";
import { JobDashboard } from "@/pages/JobDashboard";
import { MappingInspector } from "@/pages/MappingInspector";
import { SchemaDiff } from "@/pages/SchemaDiff";
import { SourceComparison } from "@/pages/SourceComparison";

const qc = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 5_000 } },
});

export default function App() {
  return (
    <QueryClientProvider client={qc}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Layout />}>
            <Route index element={<Navigate to="/jobs" replace />} />
            <Route path="connectors" element={<ConnectorWizard />} />
            <Route path="jobs" element={<JobDashboard />} />
            <Route path="jobs/:jobId/mapping" element={<MappingInspector />} />
            <Route path="jobs/:jobId/data" element={<DataPreview />} />
            <Route path="jobs/:jobId/diff" element={<SchemaDiff />} />
            <Route path="compare" element={<SourceComparison />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
