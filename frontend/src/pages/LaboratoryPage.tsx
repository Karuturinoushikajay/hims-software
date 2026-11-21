import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type LabField = {
  id: string;
  name: string;
  field_type: string;
  unit: string;
};

type LabTest = {
  id: string;
  code: string;
  name: string;
  department: string;
  price: string;
  fields: LabField[];
  is_outsourced: boolean;
};

type LabPackage = { id: string; code: string; name: string; price: string; test_ids: string[] };

type Reagent = {
  id: string;
  name: string;
  quantity_on_hand: string;
  unit: string;
  below_reorder: boolean;
};

type LabItem = {
  id: string;
  test_id: string;
  test_code: string;
  test_name: string;
  department: string;
  status: string;
  barcode: string;
  has_critical: boolean;
  has_delta: boolean;
  fields?: LabField[];
  results?: { field_id: string; field: string; value_text: string; flag: string }[];
  lab_no?: string;
  order_id?: string;
  patient_name?: string;
  uhid?: string;
};

type LabOrder = {
  id: string;
  lab_no: string;
  patient_name: string;
  uhid: string;
  bill: { bill_no: string; net_amount: string; status: string } | null;
  items: LabItem[];
};

type Catalog = {
  tests: LabTest[];
  packages: LabPackage[];
  reagents: Reagent[];
  departments: { value: string; label: string }[];
  critical: { item_id: string; lab_no: string; patient: string; test: string; status: string }[];
};

type PatientHit = { id: string; full_name: string; uhid: string; mobile: string };

const SECTIONS = ["Register", "Worklist", "Results", "Reagents", "Alerts"] as const;

export function LaboratoryPage() {
  const qc = useQueryClient();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Register");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [patientHits, setPatientHits] = useState<PatientHit[]>([]);
  const [patientId, setPatientId] = useState("");
  const [patientLabel, setPatientLabel] = useState("");
  const [testId, setTestId] = useState("");
  const [packageId, setPackageId] = useState("");
  const [department, setDepartment] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [resultValues, setResultValues] = useState<Record<string, string>>({});
  const [adjustQty, setAdjustQty] = useState("5");

  async function searchPatients(value: string) {
    setPatientQuery(value);
    if (value.trim().length < 2) {
      setPatientHits([]);
      return;
    }
    try {
      const hits = await api<PatientHit[]>(`/patients/search?q=${encodeURIComponent(value.trim())}`);
      setPatientHits(hits);
    } catch {
      setPatientHits([]);
    }
  }

  function pickPatient(hit: PatientHit) {
    setPatientId(hit.id);
    setPatientLabel(`${hit.full_name} · ${hit.uhid}`);
    setPatientQuery(`${hit.full_name} · ${hit.uhid}`);
    setPatientHits([]);
    setError(null);
  }

  const catalog = useQuery({
    queryKey: ["lab-catalog"],
    queryFn: () => api<Catalog>("/laboratory/catalog"),
  });
  const worklist = useQuery({
    queryKey: ["lab-worklist", department],
    queryFn: () =>
      api<LabItem[]>(
        `/laboratory/worklist${department ? `?department=${encodeURIComponent(department)}` : ""}`,
      ),
  });
  const orders = useQuery({
    queryKey: ["lab-orders"],
    queryFn: () => api<LabOrder[]>("/laboratory/orders"),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["lab-catalog"] });
    void qc.invalidateQueries({ queryKey: ["lab-worklist"] });
    void qc.invalidateQueries({ queryKey: ["lab-orders"] });
  };

  const tests = catalog.data?.tests || [];
  const packages = catalog.data?.packages || [];
  const reagents = catalog.data?.reagents || [];
  const activeTestId = testId || tests[0]?.id || "";
  const activePackageId = packageId || packages[0]?.id || "";

  const selectedItem = useMemo(() => {
    const fromWork = (worklist.data || []).find((i) => i.id === selectedItemId);
    if (fromWork) return fromWork;
    for (const order of orders.data || []) {
      const hit = order.items.find((i) => i.id === selectedItemId);
      if (hit) return { ...hit, lab_no: order.lab_no, order_id: order.id, patient_name: order.patient_name };
    }
    return null;
  }, [selectedItemId, worklist.data, orders.data]);

  const selectedTest = useMemo(() => {
    if (!selectedItem) return null;
    return tests.find((t) => t.id === selectedItem.test_id) || null;
  }, [selectedItem, tests]);

  const run = useMutation({
    mutationFn: (job: { path: string; json?: unknown; method?: string }) =>
      api(job.path, { method: job.method || "POST", json: job.json ?? {} }),
    onSuccess: (data: unknown, vars) => {
      setError(null);
      if (vars.path.includes("/orders") && !vars.path.includes("/pdf")) {
        const order = data as LabOrder;
        setNote(`Registered ${order.lab_no}${order.bill ? ` · bill ${order.bill.bill_no}` : ""}`);
        if (order.items[0]) setSelectedItemId(order.items[0].id);
      } else if (vars.path.includes("/results") || vars.path.includes("/amend")) {
        setNote("Results saved");
      } else if (vars.path.includes("/dispatch")) {
        setNote("Report dispatched");
      } else {
        setNote("Updated");
      }
      refresh();
    },
    onError: (err: Error) => {
      setNote(null);
      setError(err.message);
    },
  });

  function onRegister(e: FormEvent) {
    e.preventDefault();
    if (!patientId.trim()) {
      setError("Search and select a patient first");
      return;
    }
    run.mutate({
      path: "/laboratory/orders",
      json: {
        patient_id: patientId.trim(),
        test_ids: activeTestId ? [activeTestId] : [],
        paid_amount: tests.find((t) => t.id === activeTestId)?.price || "0",
      },
    });
  }

  function onRegisterPackage(e: FormEvent) {
    e.preventDefault();
    if (!patientId.trim() || !activePackageId) {
      setError("Search and select a patient, then choose a package");
      return;
    }
    const pkg = packages.find((p) => p.id === activePackageId);
    run.mutate({
      path: "/laboratory/orders",
      json: {
        patient_id: patientId.trim(),
        package_ids: [activePackageId],
        paid_amount: pkg?.price || "0",
      },
    });
  }

  function advance(path: string) {
    if (!selectedItemId) {
      setError("Select a worklist item first");
      return;
    }
    run.mutate({ path: `/laboratory/items/${selectedItemId}/${path}`, json: {} });
  }

  function saveResults(e: FormEvent) {
    e.preventDefault();
    if (!selectedItemId || !selectedTest) {
      setError("Select an item with a test");
      return;
    }
    const results = selectedTest.fields
      .filter((f) => f.field_type !== "SUB_HEADER")
      .map((f) => {
        const raw = resultValues[f.id] || "";
        if (f.field_type === "QUANTITATIVE") {
          return { field_id: f.id, value_numeric: raw, value_text: raw };
        }
        return { field_id: f.id, value_text: raw };
      });
    run.mutate({ path: `/laboratory/items/${selectedItemId}/results`, json: { results } });
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Laboratory</h1>
        <div className="flex flex-wrap gap-2">
          {SECTIONS.map((s) => (
            <Button
              key={s}
              type="button"
              variant={section === s ? "default" : "outline"}
              onClick={() => setSection(s)}
            >
              {s}
            </Button>
          ))}
        </div>
      </div>

      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {note && <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{note}</p>}

      {section === "Register" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Register test</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={onRegister}>
                <div className="relative">
                  <Label htmlFor="patient">Patient (name, MR, or mobile)</Label>
                  <Input
                    id="patient"
                    value={patientQuery}
                    placeholder="Type at least 2 characters"
                    autoComplete="off"
                    onChange={(e) => {
                      setPatientId("");
                      setPatientLabel("");
                      void searchPatients(e.target.value);
                    }}
                  />
                  {patientHits.length > 0 && (
                    <ul className="absolute z-10 mt-1 max-h-48 w-full overflow-auto rounded-md border bg-white shadow">
                      {patientHits.map((hit) => (
                        <li key={hit.id}>
                          <button
                            type="button"
                            className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                            onClick={() => pickPatient(hit)}
                          >
                            {hit.full_name} · {hit.uhid}
                            <span className="block text-xs text-slate-500">{hit.mobile}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                  {patientLabel && (
                    <p className="mt-1 text-xs text-emerald-700">Selected: {patientLabel}</p>
                  )}
                </div>
                <div>
                  <Label htmlFor="test">Test</Label>
                  <select
                    id="test"
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    value={activeTestId}
                    onChange={(e) => setTestId(e.target.value)}
                  >
                    {tests.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} — {t.name} (₹{t.price})
                        {t.is_outsourced ? " · outsourced" : ""}
                      </option>
                    ))}
                  </select>
                </div>
                <Button type="submit" disabled={run.isPending || !patientId}>
                  Register & bill
                </Button>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Register package</CardTitle>
            </CardHeader>
            <CardContent>
              <form className="space-y-3" onSubmit={onRegisterPackage}>
                <p className="text-sm text-slate-600">
                  Uses the patient selected on the left
                  {patientLabel ? `: ${patientLabel}` : " (select a patient first)"}.
                </p>
                <div>
                  <Label htmlFor="pkg">Package</Label>
                  <select
                    id="pkg"
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    value={activePackageId}
                    onChange={(e) => setPackageId(e.target.value)}
                  >
                    {packages.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.code} — {p.name} (₹{p.price})
                      </option>
                    ))}
                  </select>
                </div>
                <Button type="submit" disabled={run.isPending || !patientId}>
                  Register package
                </Button>
              </form>
              <div className="mt-4 space-y-2 text-sm">
                <p className="font-medium">Recent orders</p>
                {(orders.data || []).slice(0, 8).map((o) => (
                  <button
                    key={o.id}
                    type="button"
                    className="block w-full rounded border px-3 py-2 text-left hover:bg-slate-50"
                    onClick={() => {
                      setSelectedItemId(o.items[0]?.id || "");
                      setSection("Worklist");
                    }}
                  >
                    {o.lab_no} · {o.patient_name} · {o.items.map((i) => i.test_code).join(", ")}
                  </button>
                ))}
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {section === "Worklist" && (
        <Card>
          <CardHeader>
            <CardTitle>Department worklist</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex flex-wrap gap-2">
              <select
                className="rounded-md border px-3 py-2 text-sm"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
              >
                <option value="">All departments</option>
                {(catalog.data?.departments || []).map((d) => (
                  <option key={d.value} value={d.value}>
                    {d.label}
                  </option>
                ))}
              </select>
              <Button type="button" variant="outline" onClick={() => advance("collect")}>
                Collect
              </Button>
              <Button type="button" variant="outline" onClick={() => advance("receive")}>
                Receive
              </Button>
              <Button type="button" variant="outline" onClick={() => advance("verify")}>
                Verify
              </Button>
              <Button type="button" variant="outline" onClick={() => advance("authorize")}>
                Authorize
              </Button>
              <Button type="button" onClick={() => advance("dispatch")}>
                Dispatch
              </Button>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-slate-500">
                    <th className="py-2">Lab no</th>
                    <th>Patient</th>
                    <th>Test</th>
                    <th>Barcode</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(worklist.data || []).map((row) => (
                    <tr
                      key={row.id}
                      className={`cursor-pointer border-b ${selectedItemId === row.id ? "bg-brand-50" : ""}`}
                      onClick={() => {
                        setSelectedItemId(row.id);
                        setSection("Results");
                      }}
                    >
                      <td className="py-2">{row.lab_no}</td>
                      <td>
                        {row.patient_name}
                        <div className="text-xs text-slate-500">{row.uhid}</div>
                      </td>
                      <td>
                        {row.test_code} — {row.test_name}
                        {(row.has_critical || row.has_delta) && (
                          <div className="text-xs text-amber-700">
                            {row.has_critical ? "Critical " : ""}
                            {row.has_delta ? "Delta" : ""}
                          </div>
                        )}
                      </td>
                      <td className="font-mono text-xs">{row.barcode}</td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Results" && (
        <Card>
          <CardHeader>
            <CardTitle>
              Enter results
              {selectedItem ? ` · ${selectedItem.test_name} (${selectedItem.status})` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!selectedItem || !selectedTest ? (
              <p className="text-sm text-slate-600">Select an item from the worklist.</p>
            ) : (
              <form className="space-y-3" onSubmit={saveResults}>
                <p className="text-sm text-slate-600">
                  Barcode <span className="font-mono">{selectedItem.barcode}</span>
                  {selectedItem.order_id && (
                    <>
                      {" "}
                      ·{" "}
                      <a
                        className="text-brand-700 underline"
                        href={`/api/v1/laboratory/orders/${selectedItem.order_id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        PDF report
                      </a>
                    </>
                  )}
                </p>
                {selectedTest.fields
                  .filter((f) => f.field_type !== "SUB_HEADER")
                  .map((f) => (
                    <div key={f.id}>
                      <Label htmlFor={f.id}>
                        {f.name}
                        {f.unit ? ` (${f.unit})` : ""}
                      </Label>
                      <Input
                        id={f.id}
                        value={resultValues[f.id] || ""}
                        onChange={(e) => setResultValues((prev) => ({ ...prev, [f.id]: e.target.value }))}
                      />
                    </div>
                  ))}
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={run.isPending}>
                    Save results
                  </Button>
                  <Button type="button" variant="outline" onClick={() => advance("collect")}>
                    Collect
                  </Button>
                  <Button type="button" variant="outline" onClick={() => advance("receive")}>
                    Receive
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      {section === "Reagents" && (
        <Card>
          <CardHeader>
            <CardTitle>Reagent stock</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="space-y-2 text-sm">
              {reagents.map((r) => (
                <li key={r.id} className="flex flex-wrap items-center justify-between gap-2 rounded border px-3 py-2">
                  <span>
                    {r.name}: {r.quantity_on_hand} {r.unit}
                    {r.below_reorder ? " · low" : ""}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() =>
                      run.mutate({
                        path: "/laboratory/reagents/adjust",
                        json: {
                          reagent_id: r.id,
                          kind: "BREAKAGE",
                          delta: `-${adjustQty}`,
                          remarks: "Breakage / loss",
                        },
                      })
                    }
                  >
                    Dump {adjustQty}
                  </Button>
                </li>
              ))}
            </ul>
            <div className="max-w-xs">
              <Label htmlFor="adj">Dump quantity</Label>
              <Input id="adj" value={adjustQty} onChange={(e) => setAdjustQty(e.target.value)} />
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Alerts" && (
        <Card>
          <CardHeader>
            <CardTitle>Critical values</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-2 text-sm">
              {(catalog.data?.critical || []).map((row) => (
                <li key={row.item_id} className="rounded border border-amber-200 bg-amber-50 px-3 py-2">
                  {row.lab_no} · {row.patient} · {row.test} · {row.status}
                </li>
              ))}
              {(catalog.data?.critical || []).length === 0 && (
                <p className="text-slate-500">No critical flags right now.</p>
              )}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
