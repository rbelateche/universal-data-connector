import { afterEach, describe, expect, it } from "vitest";
import { call, captured, connect, fakeUdc, text, UDC_URL } from "./helpers.js";
import { vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
});

const TOOLS = [
  "list_sources",
  "register_source",
  "get_core_model",
  "propose_mapping",
  "update_mapping",
  "validate_mapping",
  "export_mapping",
  "get_coverage",
];

describe("tool surface", () => {
  it("exposes the eight tools with descriptions and schemas", async () => {
    fakeUdc([]);
    const client = await connect();
    const { tools } = await client.listTools();

    expect(tools.map((t) => t.name).sort()).toEqual([...TOOLS].sort());
    for (const tool of tools) {
      expect(tool.description?.length, tool.name).toBeGreaterThan(80);
      expect(tool.outputSchema, tool.name).toBeDefined();
      expect(tool.annotations?.readOnlyHint, tool.name).toBeTypeOf("boolean");
    }
    const withViews = tools.filter((t) => JSON.stringify(t._meta ?? {}).includes("ui://"));
    expect(withViews.map((t) => t.name).sort()).toEqual(["get_coverage", "propose_mapping"]);
  });

  it("describes required inputs precisely", async () => {
    fakeUdc([]);
    const client = await connect();
    const { tools } = await client.listTools();
    const update = tools.find((t) => t.name === "update_mapping")!;
    const schema = update.inputSchema as {
      required?: string[];
      properties: Record<string, { enum?: string[] }>;
    };
    expect(schema.required?.sort()).toEqual(["source_field", "source_id", "status"]);
    expect(schema.properties.status.enum).toEqual(["accepted", "rejected", "edited"]);
    expect(schema.properties.transformation.enum).toContain("parse_decimal");
  });
});

describe("list_sources", () => {
  it("summarises every source", async () => {
    fakeUdc(["list-sources"]);
    const result = await call(await connect(), "list_sources");

    expect(result.isError).toBeFalsy();
    const sources = result.structuredContent?.sources as { source_id: string }[];
    expect(sources.map((s) => s.source_id)).toEqual(["erp", "pim", "ecom"]);
    expect(text(result)).toContain("erp (needs review, 4/6 required fields)");
  });
});

describe("get_core_model", () => {
  it("returns the fields and names the required ones", async () => {
    fakeUdc(["get-schema-product"]);
    const result = await call(await connect(), "get_core_model");

    expect(result.structuredContent?.entity).toBe("Product");
    expect(text(result)).toContain(
      "required: sku, name, brand, category, price.amount, price.currency",
    );
  });
});

describe("propose_mapping", () => {
  it("returns review rows for the model and display data for the view", async () => {
    fakeUdc(["get-source-erp", "get-mapping-erp", "get-schema-product"]);
    const result = await call(await connect(), "propose_mapping", { source_id: "erp" });

    expect(result.isError).toBeFalsy();
    const sc = result.structuredContent as {
      source_name: string;
      mappings: Record<string, unknown>[];
      coverage: { missing_required: string[] };
    };
    expect(sc.source_name).toBe("SAP ERP material export");
    expect(sc.coverage.missing_required).toEqual(["brand"]);
    const mtart = sc.mappings.find((m) => m.source_field === "MTART");
    expect(mtart).toMatchObject({
      target_field: "material",
      state: "needs_review",
      status: "proposed",
      transformation: "rename",
    });
    expect(mtart).toHaveProperty("rationale");
    expect(mtart).not.toHaveProperty("source_col");

    // view-only data stays in _meta
    const meta = result._meta as {
      core_fields: { path: string }[];
      sample_values: Record<string, string[]>;
    };
    expect(meta.core_fields).toHaveLength(11);
    expect(meta.sample_values.NETPR).toContain("2.450,00");
    expect(text(result)).toContain("MTART → material (42%)");
  });

  it("runs the mapper for a source that was never mapped", async () => {
    const { calls } = fakeUdc(["get-source-wms", "err-mapping-not-yet", "err-infer-no-key"], {
      "POST /sources/wms/mapping": {
        status: captured["err-infer-no-key"].status,
        body: captured["err-infer-no-key"].body,
      },
    });
    const result = await call(await connect(), "propose_mapping", { source_id: "wms" });

    expect(calls.map((c) => c.key)).toContain("POST /sources/wms/mapping");
    expect(result.isError).toBe(true);
    expect(text(result)).toContain("ANTHROPIC_API_KEY is not set");
    expect(result._meta?.["udc/error_kind"]).toBe("unavailable");
  });

  it("explains an unknown source without a stack trace", async () => {
    fakeUdc(["err-unknown-source"]);
    const result = await call(await connect(), "propose_mapping", { source_id: "sap" });

    expect(result.isError).toBe(true);
    expect(text(result)).toBe("Unknown source_id 'sap'. Registered sources: erp, pim, ecom.");
    expect(result._meta?.["udc/error_kind"]).toBe("not_found");
  });
});

describe("update_mapping", () => {
  it("sends the decision in UDC's vocabulary and reports coverage", async () => {
    const { calls } = fakeUdc(["decide-erp-matkl"]);
    const result = await call(await connect(), "update_mapping", {
      source_id: "erp",
      source_field: "MATKL",
      status: "accepted",
    });

    expect(calls[0].key).toBe("PATCH /sources/erp/mapping/fields/MATKL");
    expect(calls[0].body).toEqual({ status: "accepted" });
    expect(text(result)).toBe(
      "MATKL → category accepted (rename). Coverage: 5/6 required fields mapped; no source field: brand.",
    );
    expect(result.structuredContent?.mapping).toMatchObject({ state: "mapped" });
  });

  it("maps edits to target_col / transform", async () => {
    const { calls } = fakeUdc([], {
      "PATCH /sources/erp/mapping/fields/NETPR": {
        status: 200,
        body: {
          ...(captured["decide-erp-matkl"].body as object),
          mapping: {
            source_col: "NETPR",
            target_col: "price.amount",
            transform: "parse_decimal",
            confidence: 0.9,
            reasoning: "Net price.",
            value_map: {},
            status: "edited",
            state: "mapped",
          },
        },
      },
    });
    await call(await connect(), "update_mapping", {
      source_id: "erp",
      source_field: "NETPR",
      status: "edited",
      transformation: "parse_decimal",
    });
    expect(calls[0].body).toEqual({ status: "edited", transform: "parse_decimal" });
  });

  it("passes UDC's list of valid targets back to the agent", async () => {
    fakeUdc(["err-edit-unknown-target"]);
    const result = await call(await connect(), "update_mapping", {
      source_id: "erp",
      source_field: "MTART",
      status: "edited",
      target_field: "material_type",
    });

    expect(result.isError).toBe(true);
    expect(text(result)).toContain("'material_type' is not a Product field. Valid fields: sku");
    expect(result._meta?.["udc/error_kind"]).toBe("invalid");
  });

  it("rejects an unknown status before calling UDC", async () => {
    const { fetchMock } = fakeUdc([]);
    const result = await call(await connect(), "update_mapping", {
      source_id: "erp",
      source_field: "MATKL",
      status: "approved",
    });

    expect(result.isError).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});

describe("validate_mapping", () => {
  it("returns issues and a one-line verdict", async () => {
    const { calls } = fakeUdc(["validate-erp"]);
    const result = await call(await connect(), "validate_mapping", { source_id: "erp" });

    expect(calls[0].key).toBe("POST /sources/erp/mapping/validate?sample_limit=5");
    const sc = result.structuredContent as { ok: boolean; issues: { code: string }[] };
    expect(sc.ok).toBe(false);
    expect(sc.issues.map((i) => i.code)).toContain("TRANSFORM_FAILED");
    expect(text(result)).toMatch(/^Not ready: 5 blocking issue\(s\), 1 warning\(s\); dry run: 0\/5/);
  });
});

describe("export_mapping", () => {
  it("returns the generated file", async () => {
    fakeUdc(["export-erp-dbt"]);
    const result = await call(await connect(), "export_mapping", {
      source_id: "erp",
      format: "dbt_sql",
    });

    const sc = result.structuredContent as { filename: string; content: string };
    expect(sc.filename).toBe("stg_erp__product.sql");
    expect(sc.content).toContain("{{ source('udc', 'erp') }}");
    expect(text(result)).toMatch(/^Generated stg_erp__product\.sql \(\d+ lines\) with \d+ warning/);
  });
});

describe("get_coverage", () => {
  it("pivots cells per field and lists required fields no source covers", async () => {
    fakeUdc(["coverage"]);
    const result = await call(await connect(), "get_coverage");

    const sc = result.structuredContent as {
      fields: { field: string; by_source: Record<string, string> }[];
      unsourced_required: string[];
    };
    const brand = sc.fields.find((f) => f.field === "brand");
    expect(brand?.by_source).toEqual({ erp: "missing", pim: "mapped", ecom: "missing" });
    expect(sc.unsourced_required).toEqual([]);
    expect(text(result)).toContain("brand ← pim");
    expect((result._meta?.cells as unknown[]).length).toBe(33);
  });
});

describe("register_source", () => {
  it("registers a source and points to the next step", async () => {
    const { calls } = fakeUdc(["register-wms"]);
    const result = await call(await connect(), "register_source", {
      source_id: "wms",
      name: "Warehouse stock export",
      system: "WMS",
      sample_rows: [{ item: "VLD-BAG-LUNE-NR", qty: 12 }],
    });

    expect(calls[0].body).toMatchObject({ source_id: "wms", target_schema: "Product" });
    expect(text(result)).toContain("Next: propose_mapping");
  });

  it("turns pydantic validation errors into one sentence", async () => {
    fakeUdc([], {
      "POST /sources": {
        status: captured["err-register-invalid"].status,
        body: captured["err-register-invalid"].body,
      },
    });
    const result = await call(await connect(), "register_source", {
      source_id: "wms",
      name: "WMS",
    });

    expect(result.isError).toBe(true);
    expect(text(result)).toBe("Provide the source's fields, some sample rows, or both.");
  });

  it("reports a taken source_id", async () => {
    fakeUdc(["err-register-duplicate"]);
    const result = await call(await connect(), "register_source", {
      source_id: "erp",
      name: "dup",
      sample_rows: [{ a: 1 }],
    });
    expect(text(result)).toContain("already exists");
    expect(result._meta?.["udc/error_kind"]).toBe("conflict");
  });
});

describe("backend failures", () => {
  it("says the backend is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("fetch failed")));
    const result = await call(await connect(), "list_sources");

    expect(result.isError).toBe(true);
    expect(text(result)).toContain(`unreachable at ${UDC_URL}`);
    expect(text(result)).not.toMatch(/\n\s+at /); // no stack trace
  });

  it("says when the backend is too slow", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockRejectedValue(new DOMException("timed out", "TimeoutError")),
    );
    const result = await call(await connect(), "list_sources");
    expect(text(result)).toBe("The UDC backend did not answer within 2s. Try again.");
    expect(result._meta?.["udc/error_kind"]).toBe("timeout");
  });

  it("handles a 500 without a JSON body", async () => {
    fakeUdc([], {
      "GET /sources": async () => new Response("Internal Server Error", { status: 500 }),
    });
    const result = await call(await connect(), "list_sources");
    expect(text(result)).toBe("The UDC backend returned HTTP 500.");
    expect(result._meta?.["udc/error_kind"]).toBe("server");
  });

  it("sends the API key when configured", async () => {
    const { calls } = fakeUdc(["list-sources"]);
    await call(await connect({ apiKey: "s3cret" }), "list_sources");
    expect(calls[0].headers.get("x-api-key")).toBe("s3cret");
  });
});
