import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type RadTest = {
  id: string;
  code: string;
  name: string;
  department: string;
  price: string;
  instruction: string;
};

type Template = {
  id: string;
  code: string;
  name: string;
  findings_template: string;
  impression_template: string;
  test_id: string;
};

type Consumable = {
  id: string;
  name: string;
  quantity_on_hand: string;
  unit: string;
  below_reorder: boolean;
};

type RadItem = {
  id: string;
  test_id: string;
  test_code: string;
  test_name: string;
  department: string;
  status: string;
  scheduled_at: string | null;
  slot_label: string;
  pacs_url: string;
  instruction?: string;
  report?: { findings: string; impression: string; version: number } | null;
  templates?: Template[];
  rad_no?: string;
  order_id?: string;
  patient_name?: string;
  uhid?: string;
};

type RadOrder = {
  id: string;
  rad_no: string;
  patient_name: string;
  uhid: string;
  bill: { bill_no: string; net_amount: string; status: string } | null;
  items: RadItem[];
};

type Catalog = {
  tests: RadTest[];
  templates: Template[];
  consumables: Consumable[];
  departments: { value: string; label: string }[];
};

type PatientHit = { id: string; full_name: string; uhid: string; mobile: string };

const SECTIONS = ["Register", "Schedule", "Worklist", "Report", "Consumables"] as const;

export function RadiologyPage() {
  const qc = useQueryClient();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Register");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [patientHits, setPatientHits] = useState<PatientHit[]>([]);
  const [patientId, setPatientId] = useState("");
  const [patientLabel, setPatientLabel] = useState("");
  const [testId, setTestId] = useState("");
  const [department, setDepartment] = useState("");
  const [selectedItemId, setSelectedItemId] = useState("");
  const [scheduleAt, setScheduleAt] = useState("");
  const [slotLabel, setSlotLabel] = useState("Morning");
  const [findings, setFindings] = useState("");
  const [impression, setImpression] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [adjustQty, setAdjustQty] = useState("5");
  const [pacsUrl, setPacsUrl] = useState("");

  const catalog = useQuery({
    queryKey: ["rad-catalog"],
    queryFn: () => api<Catalog>("/radiology/catalog"),
  });
  const worklist = useQuery({
    queryKey: ["rad-worklist", department],
    queryFn: () =>
      api<RadItem[]>(
        `/radiology/worklist${department ? `?department=${encodeURIComponent(department)}` : ""}`,
      ),
  });
  const board = useQuery({
    queryKey: ["rad-board"],
    queryFn: () => api<RadItem[]>("/radiology/schedule-board"),
  });
  const orders = useQuery({
    queryKey: ["rad-orders"],
    queryFn: () => api<RadOrder[]>("/radiology/orders"),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["rad-catalog"] });
    void qc.invalidateQueries({ queryKey: ["rad-worklist"] });
    void qc.invalidateQueries({ queryKey: ["rad-board"] });
    void qc.invalidateQueries({ queryKey: ["rad-orders"] });
  };

  const tests = catalog.data?.tests || [];
  const activeTestId = testId || tests[0]?.id || "";

  const selectedItem = useMemo(() => {
    const pools = [...(worklist.data || []), ...(board.data || [])];
    const fromList = pools.find((i) => i.id === selectedItemId);
    if (fromList) return fromList;
    for (const order of orders.data || []) {
      const hit = order.items.find((i) => i.id === selectedItemId);
      if (hit) {
        return {
          ...hit,
          rad_no: order.rad_no,
          order_id: order.id,
          patient_name: order.patient_name,
          uhid: order.uhid,
        };
      }
    }
    return null;
  }, [selectedItemId, worklist.data, board.data, orders.data]);

  const detail = useQuery({
    queryKey: ["rad-order-detail", selectedItem?.order_id],
    enabled: Boolean(selectedItem?.order_id),
    queryFn: () => api<RadOrder>(`/radiology/orders/${selectedItem!.order_id}`),
  });

  const detailedItem = useMemo(() => {
    if (!selectedItemId || !detail.data) return selectedItem;
    const hit = detail.data.items.find((i) => i.id === selectedItemId);
    if (!hit) return selectedItem;
    return {
      ...hit,
      rad_no: detail.data.rad_no,
      order_id: detail.data.id,
      patient_name: detail.data.patient_name,
      uhid: detail.data.uhid,
    };
  }, [selectedItemId, detail.data, selectedItem]);

  async function searchPatients(value: string) {
    setPatientQuery(value);
    if (value.trim().length < 2) {
      setPatientHits([]);
      return;
    }
    try {
      setPatientHits(await api<PatientHit[]>(`/patients/search?q=${encodeURIComponent(value.trim())}`));
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

  const run = useMutation({
    mutationFn: (job: { path: string; json?: unknown; method?: string }) =>
      api(job.path, { method: job.method || "POST", json: job.json ?? {} }),
    onSuccess: (data: unknown, vars) => {
      setError(null);
      if (vars.path.endsWith("/orders") && !vars.path.includes("/pdf")) {
        const order = data as RadOrder;
        setNote(`Registered ${order.rad_no}${order.bill ? ` · bill ${order.bill.bill_no}` : ""}`);
        if (order.items[0]) setSelectedItemId(order.items[0].id);
      } else if (vars.path.includes("/report")) {
        setNote("Report saved");
      } else if (vars.path.includes("/dispatch")) {
        setNote("Report dispatched");
      } else {
        setNote("Updated");
      }
      refresh();
      void qc.invalidateQueries({ queryKey: ["rad-order-detail"] });
    },
    onError: (err: Error) => {
      setNote(null);
      setError(err.message);
    },
  });

  function onRegister(e: FormEvent) {
    e.preventDefault();
    if (!patientId) {
      setError("Search and select a patient first");
      return;
    }
    run.mutate({
      path: "/radiology/orders",
      json: {
        patient_id: patientId,
        test_ids: [activeTestId],
        paid_amount: tests.find((t) => t.id === activeTestId)?.price || "0",
      },
    });
  }

  function applyTemplate(id: string) {
    setTemplateId(id);
    const tpl =
      (detailedItem?.templates || catalog.data?.templates || []).find((t) => t.id === id) || null;
    if (tpl) {
      setFindings(tpl.findings_template);
      setImpression(tpl.impression_template);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Radiology</h1>
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
              <CardTitle>Register study</CardTitle>
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
                  {patientLabel && <p className="mt-1 text-xs text-emerald-700">Selected: {patientLabel}</p>}
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
              <CardTitle>Recent orders</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(orders.data || []).slice(0, 10).map((o) => (
                <button
                  key={o.id}
                  type="button"
                  className="block w-full rounded border px-3 py-2 text-left hover:bg-slate-50"
                  onClick={() => {
                    setSelectedItemId(o.items[0]?.id || "");
                    setSection("Worklist");
                  }}
                >
                  {o.rad_no} · {o.patient_name} · {o.items.map((i) => i.test_code).join(", ")}
                </button>
              ))}
            </CardContent>
          </Card>
        </div>
      )}

      {section === "Schedule" && (
        <Card>
          <CardHeader>
            <CardTitle>Today&apos;s schedule board</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <form
              className="flex flex-wrap items-end gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                if (!selectedItemId || !scheduleAt) {
                  setError("Select an item and set date/time");
                  return;
                }
                run.mutate({
                  path: `/radiology/items/${selectedItemId}/schedule`,
                  json: { scheduled_at: scheduleAt, slot_label: slotLabel },
                });
              }}
            >
              <div>
                <Label htmlFor="when">Schedule at</Label>
                <Input
                  id="when"
                  type="datetime-local"
                  value={scheduleAt}
                  onChange={(e) => setScheduleAt(e.target.value)}
                />
              </div>
              <div>
                <Label htmlFor="slot">Slot</Label>
                <Input id="slot" value={slotLabel} onChange={(e) => setSlotLabel(e.target.value)} />
              </div>
              <Button type="submit">Schedule selected</Button>
            </form>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-slate-500">
                    <th className="py-2">Time</th>
                    <th>Rad no</th>
                    <th>Patient</th>
                    <th>Test</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {(board.data || []).map((row) => (
                    <tr
                      key={row.id}
                      className={`cursor-pointer border-b ${selectedItemId === row.id ? "bg-brand-50" : ""}`}
                      onClick={() => setSelectedItemId(row.id)}
                    >
                      <td className="py-2">{row.scheduled_at ? new Date(row.scheduled_at).toLocaleString() : "—"}</td>
                      <td>{row.rad_no}</td>
                      <td>{row.patient_name}</td>
                      <td>
                        {row.test_code} — {row.test_name}
                      </td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Worklist" && (
        <Card>
          <CardHeader>
            <CardTitle>Acquisition worklist</CardTitle>
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
              <Button type="button" variant="outline" onClick={() => run.mutate({ path: `/radiology/items/${selectedItemId}/start` })}>
                Start
              </Button>
              <Button
                type="button"
                onClick={() =>
                  run.mutate({
                    path: `/radiology/items/${selectedItemId}/complete`,
                    json: { pacs_url: pacsUrl || undefined },
                  })
                }
              >
                Complete acquisition
              </Button>
            </div>
            <div>
              <Label htmlFor="pacs">Optional PACS link-out</Label>
              <Input id="pacs" value={pacsUrl} onChange={(e) => setPacsUrl(e.target.value)} placeholder="https://pacs.example/study/…" />
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-slate-500">
                    <th className="py-2">Rad no</th>
                    <th>Patient</th>
                    <th>Test</th>
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
                        setSection("Report");
                      }}
                    >
                      <td className="py-2">{row.rad_no}</td>
                      <td>
                        {row.patient_name}
                        <div className="text-xs text-slate-500">{row.uhid}</div>
                      </td>
                      <td>
                        {row.test_code} — {row.test_name}
                      </td>
                      <td>{row.status}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Report" && (
        <Card>
          <CardHeader>
            <CardTitle>
              Report
              {detailedItem ? ` · ${detailedItem.test_name} (${detailedItem.status})` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!detailedItem ? (
              <p className="text-sm text-slate-600">Select an item from the worklist.</p>
            ) : (
              <form
                className="space-y-3"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  run.mutate({
                    path: `/radiology/items/${detailedItem.id}/report`,
                    json: {
                      template_id: templateId || undefined,
                      findings,
                      impression,
                    },
                  });
                }}
              >
                <p className="text-sm text-slate-600">
                  {detailedItem.rad_no} · {detailedItem.patient_name}
                  {detailedItem.order_id && (
                    <>
                      {" "}
                      ·{" "}
                      <a
                        className="text-brand-700 underline"
                        href={`/api/v1/radiology/orders/${detailedItem.order_id}/pdf`}
                        target="_blank"
                        rel="noreferrer"
                      >
                        PDF report
                      </a>
                    </>
                  )}
                </p>
                {detailedItem.instruction && (
                  <p className="rounded bg-slate-50 p-2 text-xs text-slate-600">{detailedItem.instruction}</p>
                )}
                <div>
                  <Label htmlFor="tpl">Template</Label>
                  <select
                    id="tpl"
                    className="w-full rounded-md border px-3 py-2 text-sm"
                    value={templateId}
                    onChange={(e) => applyTemplate(e.target.value)}
                  >
                    <option value="">— none —</option>
                    {(detailedItem.templates || catalog.data?.templates || []).map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.code} — {t.name}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor="findings">Findings</Label>
                  <textarea
                    id="findings"
                    className="min-h-28 w-full rounded-md border px-3 py-2 text-sm"
                    value={findings}
                    onChange={(e) => setFindings(e.target.value)}
                  />
                </div>
                <div>
                  <Label htmlFor="impression">Impression</Label>
                  <textarea
                    id="impression"
                    className="min-h-20 w-full rounded-md border px-3 py-2 text-sm"
                    value={impression}
                    onChange={(e) => setImpression(e.target.value)}
                  />
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={run.isPending}>
                    Save report
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => run.mutate({ path: `/radiology/items/${detailedItem.id}/authorize` })}
                  >
                    Authorize
                  </Button>
                  <Button type="button" onClick={() => run.mutate({ path: `/radiology/items/${detailedItem.id}/dispatch` })}>
                    Dispatch
                  </Button>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      )}

      {section === "Consumables" && (
        <Card>
          <CardHeader>
            <CardTitle>Consumable stock</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <ul className="space-y-2 text-sm">
              {(catalog.data?.consumables || []).map((r) => (
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
                        path: "/radiology/consumables/adjust",
                        json: {
                          consumable_id: r.id,
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
    </div>
  );
}
