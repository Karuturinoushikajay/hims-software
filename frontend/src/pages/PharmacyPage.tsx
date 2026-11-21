import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Drug = {
  id: string;
  code: string;
  name: string;
  selling_price: string;
  quantity_on_hand: number;
  below_reorder: boolean;
  schedule: string;
  reorder_level: number;
};

type Supplier = { id: string; name: string };
type Batch = {
  id: string;
  drug: string;
  batch_no: string;
  expiry_date: string;
  quantity_on_hand: number;
  near_expiry: boolean;
};
type Inventory = {
  drugs: Drug[];
  batches: Batch[];
  low_stock: Drug[];
  near_expiry: Batch[];
  controlled_register: { drug: string; schedule: string; quantity: number; sale_no: string; at: string }[];
};
type PO = {
  id: string;
  po_no: string;
  status: string;
  supplier_id: string;
  lines: { id: string; drug_id: string; drug: string; quantity: number; received_quantity: number }[];
};
type SaleResult = {
  sale_no: string;
  lines: { id: string; drug: string; batch_no: string; quantity: number }[];
  bill: { bill_no: string; net_amount: string; status: string } | null;
};

const SECTIONS = ["Stock", "Purchase", "Dispense", "Adjust", "Alerts"] as const;

export function PharmacyPage() {
  const qc = useQueryClient();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Stock");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const inventory = useQuery({
    queryKey: ["pharmacy-inventory"],
    queryFn: () => api<Inventory>("/pharmacy/inventory"),
  });
  const suppliers = useQuery({
    queryKey: ["pharmacy-suppliers"],
    queryFn: () => api<Supplier[]>("/pharmacy/suppliers"),
  });
  const purchaseOrders = useQuery({
    queryKey: ["pharmacy-pos"],
    queryFn: () => api<PO[]>("/pharmacy/purchase-orders"),
  });

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["pharmacy-inventory"] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-pos"] });
    void qc.invalidateQueries({ queryKey: ["pharmacy-suppliers"] });
  };

  const drugs = inventory.data?.drugs || [];
  const defaultDrugId = drugs[0]?.id || "";
  const defaultSupplierId = suppliers.data?.[0]?.id || "";

  const [drugId, setDrugId] = useState("");
  const [qty, setQty] = useState("10");
  const [patientId, setPatientId] = useState("");
  const [batchNo, setBatchNo] = useState("B1");
  const [expiry, setExpiry] = useState("");
  const [poQty, setPoQty] = useState("100");
  const [supplierName, setSupplierName] = useState("");
  const [adjustBatchId, setAdjustBatchId] = useState("");
  const [adjustQty, setAdjustQty] = useState("1");
  const [newDrug, setNewDrug] = useState({ code: "", name: "", selling_price: "5.00", reorder_level: "20" });

  const activeDrugId = drugId || defaultDrugId;
  const activeSupplierId = defaultSupplierId;
  const openPo = useMemo(
    () => (purchaseOrders.data || []).find((p) => p.status === "OPEN" || p.status === "PARTIAL"),
    [purchaseOrders.data],
  );

  const run = useMutation({
    mutationFn: (job: { path: string; json: unknown; method?: string }) =>
      api(job.path, { method: job.method || "POST", json: job.json }),
    onSuccess: (data: unknown) => {
      setError(null);
      const sale = data as SaleResult;
      if (sale?.sale_no) {
        setNote(
          `Sale ${sale.sale_no}` +
            (sale.bill ? ` · bill ${sale.bill.bill_no} · ${sale.bill.net_amount} · ${sale.bill.status}` : ""),
        );
      } else {
        setNote("Saved.");
      }
      refresh();
    },
    onError: (e: Error) => setError(e.message),
  });

  if (inventory.error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
        {(inventory.error as Error).message}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Pharmacy</h1>
        <select
          aria-label="Pharmacy section"
          className="h-9 rounded-md border px-2 text-sm"
          value={section}
          onChange={(e) => {
            setSection(e.target.value as (typeof SECTIONS)[number]);
            setError(null);
            setNote(null);
          }}
        >
          {SECTIONS.map((name) => (
            <option key={name}>{name}</option>
          ))}
        </select>
      </div>
      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
          {error}
        </div>
      )}
      {note && <p className="text-sm text-emerald-700">{note}</p>}

      {section === "Stock" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Drug master</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <form
                className="grid gap-2"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  run.mutate({ path: "/pharmacy/drugs", json: newDrug });
                }}
              >
                <Input aria-label="Drug code" placeholder="Code" value={newDrug.code} onChange={(e) => setNewDrug({ ...newDrug, code: e.target.value })} required />
                <Input aria-label="Drug name" placeholder="Name" value={newDrug.name} onChange={(e) => setNewDrug({ ...newDrug, name: e.target.value })} required />
                <Input aria-label="Selling price" placeholder="Selling price" value={newDrug.selling_price} onChange={(e) => setNewDrug({ ...newDrug, selling_price: e.target.value })} />
                <Input aria-label="Reorder level" placeholder="Reorder level" value={newDrug.reorder_level} onChange={(e) => setNewDrug({ ...newDrug, reorder_level: e.target.value })} />
                <Button type="submit">Add drug</Button>
              </form>
              <ul className="max-h-80 space-y-1 overflow-auto text-sm">
                {drugs.map((d) => (
                  <li key={d.id} className="border-b border-slate-100 py-1">
                    {d.code} · {d.name} · stock {d.quantity_on_hand}
                    {d.below_reorder ? " · low" : ""} · ₹{d.selling_price}
                  </li>
                ))}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Batches on hand</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="max-h-96 space-y-1 overflow-auto text-sm">
                {(inventory.data?.batches || []).map((b) => (
                  <li key={b.id} className="border-b border-slate-100 py-1">
                    {b.drug} · {b.batch_no} · exp {b.expiry_date} · qty {b.quantity_on_hand}
                    {b.near_expiry ? " · near expiry" : ""}
                  </li>
                ))}
                {!inventory.data?.batches?.length && <li className="text-slate-500">No stock yet. Receive a GRN first.</li>}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}

      {section === "Purchase" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Supplier and purchase order</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <form
                className="flex gap-2"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  run.mutate({ path: "/pharmacy/suppliers", json: { name: supplierName } });
                  setSupplierName("");
                }}
              >
                <Input aria-label="Supplier name" placeholder="New supplier" value={supplierName} onChange={(e) => setSupplierName(e.target.value)} required />
                <Button type="submit" variant="outline">
                  Add
                </Button>
              </form>
              <form
                className="grid gap-2"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  run.mutate({
                    path: "/pharmacy/purchase-orders",
                    json: {
                      supplier_id: activeSupplierId,
                      lines: [{ drug_id: activeDrugId, quantity: Number(poQty), unit_cost: drugs.find((d) => d.id === activeDrugId)?.selling_price || "1" }],
                    },
                  });
                }}
              >
                <Label>Create PO</Label>
                <select aria-label="PO drug" className="h-10 rounded-md border px-2 text-sm" value={activeDrugId} onChange={(e) => setDrugId(e.target.value)}>
                  {drugs.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <Input aria-label="PO quantity" value={poQty} onChange={(e) => setPoQty(e.target.value)} />
                <Button type="submit">Create purchase order</Button>
              </form>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Goods receipt (GRN)</CardTitle>
            </CardHeader>
            <CardContent>
              <form
                className="grid gap-2"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  const line: Record<string, string | number> = {
                    drug_id: activeDrugId,
                    batch_no: batchNo,
                    expiry_date: expiry,
                    quantity: Number(poQty),
                    unit_cost: "1.00",
                  };
                  if (openPo) {
                    const poLine = openPo.lines.find((l) => l.drug_id === activeDrugId) || openPo.lines[0];
                    if (poLine) line.purchase_order_line_id = poLine.id;
                  }
                  run.mutate({
                    path: "/pharmacy/grn",
                    json: {
                      supplier_id: openPo?.supplier_id || activeSupplierId,
                      purchase_order_id: openPo?.id,
                      invoice_no: "INV-UI",
                      lines: [line],
                    },
                  });
                }}
              >
                <p className="text-sm text-slate-600">{openPo ? `Against ${openPo.po_no} (${openPo.status})` : "Direct receipt without an open PO."}</p>
                <select aria-label="GRN drug" className="h-10 rounded-md border px-2 text-sm" value={activeDrugId} onChange={(e) => setDrugId(e.target.value)}>
                  {drugs.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
                <Input aria-label="Batch number" placeholder="Batch" value={batchNo} onChange={(e) => setBatchNo(e.target.value)} required />
                <Input aria-label="Expiry date" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} required />
                <Input aria-label="Receive quantity" value={poQty} onChange={(e) => setPoQty(e.target.value)} />
                <Button type="submit">Receive goods</Button>
              </form>
            </CardContent>
          </Card>
        </div>
      )}

      {section === "Dispense" && (
        <Card>
          <CardHeader>
            <CardTitle>Counter / patient sale (FEFO)</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid max-w-xl gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                run.mutate({
                  path: "/pharmacy/sales",
                  json: {
                    kind: "COUNTER",
                    patient_id: patientId || null,
                    paid_amount: patientId ? String(Number(qty) * Number(drugs.find((d) => d.id === activeDrugId)?.selling_price || 0)) : undefined,
                    items: [{ drug_id: activeDrugId, quantity: Number(qty) }],
                  },
                });
              }}
            >
              <select aria-label="Sale drug" className="h-10 rounded-md border px-2 text-sm" value={activeDrugId} onChange={(e) => setDrugId(e.target.value)}>
                {drugs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} · stock {d.quantity_on_hand} · ₹{d.selling_price}
                  </option>
                ))}
              </select>
              <Input aria-label="Sale quantity" value={qty} onChange={(e) => setQty(e.target.value)} />
              <Input aria-label="Patient id" placeholder="Patient UUID (optional for bill)" value={patientId} onChange={(e) => setPatientId(e.target.value)} />
              <p className="text-xs text-slate-500">Earliest-expiry batch is used first. Schedule H1 / narcotic sales write the controlled register.</p>
              <Button type="submit">Dispense</Button>
            </form>
          </CardContent>
        </Card>
      )}

      {section === "Adjust" && (
        <Card>
          <CardHeader>
            <CardTitle>Dump / write-off</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid max-w-xl gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                run.mutate({
                  path: "/pharmacy/adjust",
                  json: {
                    batch_id: adjustBatchId || inventory.data?.batches[0]?.id,
                    kind: "DUMP",
                    quantity: Number(adjustQty),
                    remarks: "Damaged / expired dump",
                  },
                });
              }}
            >
              <select
                aria-label="Batch to dump"
                className="h-10 rounded-md border px-2 text-sm"
                value={adjustBatchId || inventory.data?.batches[0]?.id || ""}
                onChange={(e) => setAdjustBatchId(e.target.value)}
              >
                {(inventory.data?.batches || []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.drug} · {b.batch_no} · qty {b.quantity_on_hand}
                  </option>
                ))}
              </select>
              <Input aria-label="Dump quantity" value={adjustQty} onChange={(e) => setAdjustQty(e.target.value)} />
              <Button type="submit" variant="outline">
                Dump stock
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {section === "Alerts" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Low stock</CardTitle>
            </CardHeader>
            <CardContent className="text-sm">
              <ul className="space-y-1">
                {(inventory.data?.low_stock || []).map((d) => (
                  <li key={d.id}>
                    {d.name} · {d.quantity_on_hand} / reorder {d.reorder_level}
                  </li>
                ))}
                {!inventory.data?.low_stock?.length && <li className="text-slate-500">None</li>}
              </ul>
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>Near expiry and controlled register</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <ul className="space-y-1">
                {(inventory.data?.near_expiry || []).map((b) => (
                  <li key={b.id}>
                    {b.drug} · {b.batch_no} · {b.expiry_date}
                  </li>
                ))}
                {!inventory.data?.near_expiry?.length && <li className="text-slate-500">No near-expiry batches</li>}
              </ul>
              <ul className="space-y-1 border-t border-slate-100 pt-2">
                {(inventory.data?.controlled_register || []).map((e, index) => (
                  <li key={`${e.sale_no}-${index}`}>
                    {e.schedule} · {e.drug} x {e.quantity} · {e.sale_no}
                  </li>
                ))}
                {!inventory.data?.controlled_register?.length && <li className="text-slate-500">No controlled issues yet</li>}
              </ul>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
