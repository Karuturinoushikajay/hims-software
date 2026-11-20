import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Hit = { id: string; full_name: string; uhid: string; mobile: string };
type Bill = {
  id: string;
  bill_no: string;
  net_amount: string;
  due_amount: string;
  paid_amount: string;
  status: string;
  tax_amount: string;
  gst_applied: boolean;
};
type Advance = { id: string; advance_no: string; amount: string; balance: string; mode: string };
type Shift = {
  status: string;
  opening_cash: string;
  expected_cash: string | null;
  variance: string | null;
};
type ShiftResponse = { shift: Shift | null };
type RefundRow = { id: string; amount: string; reason: string; status: string; bill_id: string };
type DiscountRow = { id: string; patient_name: string; uhid: string; discount_type: string; discount_value: string };

const modes = ["CASH", "UPI", "CARD", "CHEQUE", "TRANSFER"];

export function BillingPage() {
  const qc = useQueryClient();
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [patient, setPatient] = useState<Hit | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const shift = useQuery({
    queryKey: ["shift"],
    queryFn: () => api<ShiftResponse>("/billing/shifts"),
  });
  const bills = useQuery({
    queryKey: ["bills", patient?.id],
    queryFn: () => api<Bill[]>(`/billing/bills?patient_id=${patient?.id}`),
    enabled: Boolean(patient),
  });
  const advances = useQuery({
    queryKey: ["advances", patient?.id],
    queryFn: () => api<Advance[]>(`/billing/advances?patient_id=${patient?.id}`),
    enabled: Boolean(patient),
  });
  const refunds = useQuery({
    queryKey: ["refunds-pending"],
    queryFn: () => api<RefundRow[]>("/billing/refunds"),
  });
  const discounts = useQuery({
    queryKey: ["discount-requests"],
    queryFn: () => api<DiscountRow[]>("/billing/discount-requests"),
    retry: false,
  });
  const taxes = useQuery({
    queryKey: ["tax-categories"],
    queryFn: () =>
      api<{ id: string; name: string; rate_percent: string; gst_confirmed: boolean }[]>("/billing/tax-categories"),
  });

  function refresh() {
    void qc.invalidateQueries({ queryKey: ["bills"] });
    void qc.invalidateQueries({ queryKey: ["advances"] });
    void qc.invalidateQueries({ queryKey: ["refunds-pending"] });
    void qc.invalidateQueries({ queryKey: ["shift"] });
    void qc.invalidateQueries({ queryKey: ["discount-requests"] });
  }

  async function run(action: () => Promise<unknown>, ok: string) {
    setError(null);
    setMessage(null);
    try {
      await action();
      setMessage(ok);
      refresh();
    } catch (err) {
      setError((err as Error).message);
    }
  }

  async function search(value: string) {
    setQuery(value);
    if (value.trim().length < 2) {
      setHits([]);
      return;
    }
    setHits(await api<Hit[]>(`/patients/search?q=${encodeURIComponent(value)}`).catch(() => []));
  }

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <h1 className="text-2xl font-semibold">Billing</h1>
      {taxes.data && !taxes.data[0]?.gst_confirmed && (
        <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-900">
          GSTIN is not confirmed, so tax on new bills is zero. Referral TDS is also withheld until an accountant confirms the rate.
        </p>
      )}
      {message && <p className="text-sm text-emerald-700">{message}</p>}
      {error && <p className="text-sm text-red-600">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle>Cash shift and day close</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3 text-sm">
          {shift.data?.shift ? (
            <p>Open shift. Opening cash {shift.data.shift.opening_cash}.</p>
          ) : (
            <form
              className="flex items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const opening_cash = new FormData(e.currentTarget).get("opening_cash");
                void run(
                  () => api("/billing/shifts", { method: "POST", json: { opening_cash } }),
                  "Shift opened.",
                );
              }}
            >
              <div>
                <Label htmlFor="opening_cash">Opening cash</Label>
                <Input id="opening_cash" name="opening_cash" defaultValue="0.00" required />
              </div>
              <Button type="submit">Open shift</Button>
            </form>
          )}
          {shift.data?.shift && (
            <form
              className="flex items-end gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                const counted_cash = new FormData(e.currentTarget).get("counted_cash");
                void (async () => {
                  setError(null);
                  setMessage(null);
                  try {
                    const closed = await api<Shift>("/billing/shifts/close", { method: "POST", json: { counted_cash } });
                    setMessage(`Shift closed. Expected ${closed?.expected_cash}, variance ${closed?.variance}.`);
                    refresh();
                  } catch (err) {
                    setError((err as Error).message);
                  }
                })();
              }}
            >
              <div>
                <Label htmlFor="counted_cash">Counted cash</Label>
                <Input id="counted_cash" name="counted_cash" required />
              </div>
              <Button type="submit" variant="outline">
                Close shift
              </Button>
            </form>
          )}
          <Button
            type="button"
            variant="outline"
            onClick={() => void run(() => api("/billing/day-close", { method: "POST", json: {} }), "Day closed.")}
          >
            Close day
          </Button>
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              void run(() => api("/billing/day-close", { method: "POST", json: { reopen: true } }), "Day reopened.")
            }
          >
            Reopen today
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Find the patient</CardTitle>
        </CardHeader>
        <CardContent>
          <Label htmlFor="find">Name, MR number, or mobile</Label>
          <Input id="find" value={query} autoComplete="off" onChange={(e) => void search(e.target.value)} />
          {hits.length > 0 && (
            <ul className="mt-2 rounded-md border">
              {hits.map((hit) => (
                <li key={hit.id}>
                  <button
                    type="button"
                    className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                    onClick={() => {
                      setPatient(hit);
                      setHits([]);
                      setQuery(`${hit.full_name} · ${hit.uhid}`);
                    }}
                  >
                    {hit.full_name} · {hit.uhid} · {hit.mobile}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      {patient && (
        <>
          <Card>
            <CardHeader>
              <CardTitle>
                Bills for {patient.full_name}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm">
              {(bills.data || []).length === 0 && <p className="text-slate-500">No bills yet.</p>}
              {(bills.data || []).map((bill) => (
                <div key={bill.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <span className="font-mono font-semibold">{bill.bill_no}</span> · {bill.status} · net {bill.net_amount} · due{" "}
                      {bill.due_amount}
                      {bill.gst_applied && ` · GST ${bill.tax_amount}`}
                    </div>
                    <div className="flex gap-3">
                      <a className="text-brand-700 underline" href={`/api/v1/billing/bills/${bill.id}/pdf?layout=a4&doc=invoice`} target="_blank" rel="noreferrer">
                        A4 invoice
                      </a>
                      <a className="text-brand-700 underline" href={`/api/v1/billing/bills/${bill.id}/pdf?layout=thermal&doc=receipt`} target="_blank" rel="noreferrer">
                        Thermal receipt
                      </a>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-4">
                    <MiniForm
                      idPrefix={`collect-${bill.id}`}
                      label="Collect due"
                      onSubmit={(amount, mode) =>
                        run(
                          () => api("/billing/collect", { method: "POST", json: { bill_id: bill.id, amount, mode } }),
                          "Payment collected.",
                        )
                      }
                    />
                    <MiniForm
                      idPrefix={`refund-${bill.id}`}
                      label="Refund"
                      withReason
                      onSubmit={(amount, mode, reason) =>
                        run(
                          () =>
                            api("/billing/refunds", {
                              method: "POST",
                              json: { bill_id: bill.id, amount, mode, reason },
                            }),
                          "Refund recorded.",
                        )
                      }
                    />
                    <form
                      className="flex items-end gap-2"
                      onSubmit={(e: FormEvent<HTMLFormElement>) => {
                        e.preventDefault();
                        const reason = String(new FormData(e.currentTarget).get("reason") || "");
                        void run(
                          () => api(`/billing/bills/${bill.id}/cancel`, { method: "POST", json: { reason, mode: "CASH" } }),
                          "Bill cancelled.",
                        );
                      }}
                    >
                      <div>
                        <Label htmlFor={`cancel-${bill.id}`}>Cancel reason</Label>
                        <Input id={`cancel-${bill.id}`} name="reason" required />
                      </div>
                      <Button type="submit" variant="danger" size="sm">
                        Cancel bill
                      </Button>
                    </form>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Advance</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3 text-sm">
                <form
                  className="flex flex-wrap items-end gap-2"
                  onSubmit={(e: FormEvent<HTMLFormElement>) => {
                    e.preventDefault();
                    const form = new FormData(e.currentTarget);
                    void run(
                      () =>
                        api("/billing/advances", {
                          method: "POST",
                          json: { patient_id: patient.id, amount: form.get("amount"), mode: form.get("mode") },
                        }),
                      "Advance received.",
                    );
                    e.currentTarget.reset();
                  }}
                >
                  <div>
                    <Label htmlFor="advance_amount">Amount</Label>
                    <Input id="advance_amount" name="amount" required />
                  </div>
                  <ModeSelect id="advance_mode" />
                  <Button type="submit" size="sm">
                    Take advance
                  </Button>
                </form>
                {(advances.data || []).map((row) => (
                  <div key={row.id} className="rounded-md border p-2">
                    <p>
                      {row.advance_no} · balance {row.balance} of {row.amount}
                    </p>
                    {(bills.data || [])
                      .filter((bill) => Number(bill.due_amount) > 0)
                      .map((bill) => (
                        <form
                          key={bill.id}
                          className="mt-2 flex items-end gap-2"
                          onSubmit={(e: FormEvent<HTMLFormElement>) => {
                            e.preventDefault();
                            const amount = new FormData(e.currentTarget).get("amount");
                            void run(
                              () =>
                                api(`/billing/advances/${row.id}/apply`, {
                                  method: "POST",
                                  json: { bill_id: bill.id, amount },
                                }),
                              "Advance applied.",
                            );
                          }}
                        >
                          <Input name="amount" placeholder={`Apply to ${bill.bill_no}`} required />
                          <Button type="submit" size="sm" variant="outline">
                            Apply
                          </Button>
                        </form>
                      ))}
                  </div>
                ))}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Raise a service bill</CardTitle>
              </CardHeader>
              <CardContent>
                <form
                  className="grid gap-2 text-sm"
                  onSubmit={(e: FormEvent<HTMLFormElement>) => {
                    e.preventDefault();
                    const form = new FormData(e.currentTarget);
                    const amount = String(form.get("amount") || "");
                    void run(
                      () =>
                        api("/billing/charges", {
                          method: "POST",
                          json: {
                            patient_id: patient.id,
                            description: form.get("description"),
                            amount,
                            hospital_share: amount,
                            doctor_share: "0.00",
                            tax_category_id: form.get("tax_category_id") || null,
                            paid_amount: form.get("paid_amount") || "0.00",
                            mode: form.get("mode"),
                          },
                        }),
                      "Bill posted.",
                    );
                    e.currentTarget.reset();
                  }}
                >
                  <div>
                    <Label htmlFor="description">Description</Label>
                    <Input id="description" name="description" required />
                  </div>
                  <div>
                    <Label htmlFor="charge_amount">Amount</Label>
                    <Input id="charge_amount" name="amount" required />
                  </div>
                  <div>
                    <Label htmlFor="paid_amount">Collected now</Label>
                    <Input id="paid_amount" name="paid_amount" defaultValue="0.00" />
                  </div>
                  <div>
                    <Label htmlFor="tax_category_id">Tax category</Label>
                    <select id="tax_category_id" name="tax_category_id" className="h-10 w-full rounded-md border px-2">
                      <option value="">No tax</option>
                      {(taxes.data || []).map((tax) => (
                        <option key={tax.id} value={tax.id}>
                          {tax.name} · {tax.rate_percent}%
                        </option>
                      ))}
                    </select>
                  </div>
                  <ModeSelect id="charge_mode" />
                  <Button type="submit">Post bill</Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {(refunds.data || []).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Refunds waiting for authorization</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {refunds.data?.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2">
                <span>
                  {row.amount} · {row.reason}
                </span>
                <span className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      void run(
                        () => api(`/billing/refunds/${row.id}/authorize`, { method: "POST", json: { approve: true } }),
                        "Refund authorized.",
                      )
                    }
                  >
                    Authorize
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void run(
                        () => api(`/billing/refunds/${row.id}/authorize`, { method: "POST", json: { approve: false } }),
                        "Refund rejected.",
                      )
                    }
                  >
                    Reject
                  </Button>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {(discounts.data || []).length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Discount requests</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {discounts.data?.map((row) => (
              <div key={row.id} className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-2">
                <span>
                  {row.patient_name} · {row.uhid} · {row.discount_type} {row.discount_value}
                </span>
                <span className="flex gap-2">
                  <Button
                    size="sm"
                    onClick={() =>
                      void run(
                        () =>
                          api(`/billing/discount-requests/${row.id}/decide`, {
                            method: "POST",
                            json: { approve: true },
                          }),
                        "Discount approved and consultation posted.",
                      )
                    }
                  >
                    Approve
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() =>
                      void run(
                        () =>
                          api(`/billing/discount-requests/${row.id}/decide`, {
                            method: "POST",
                            json: { approve: false },
                          }),
                        "Discount rejected.",
                      )
                    }
                  >
                    Reject
                  </Button>
                </span>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function ModeSelect({ id }: { id: string }) {
  return (
    <div>
      <Label htmlFor={id}>Mode</Label>
      <select id={id} name="mode" className="h-10 rounded-md border px-2 text-sm">
        {modes.map((mode) => (
          <option key={mode} value={mode}>
            {mode}
          </option>
        ))}
      </select>
    </div>
  );
}

function MiniForm({
  idPrefix,
  label,
  withReason,
  onSubmit,
}: {
  idPrefix: string;
  label: string;
  withReason?: boolean;
  onSubmit: (amount: string, mode: string, reason: string) => void;
}) {
  return (
    <form
      className="flex flex-wrap items-end gap-2"
      onSubmit={(e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        const form = new FormData(e.currentTarget);
        onSubmit(String(form.get("amount") || ""), String(form.get("mode") || "CASH"), String(form.get("reason") || ""));
        e.currentTarget.reset();
      }}
    >
      <div>
        <Label htmlFor={`${idPrefix}-amount`}>{label}</Label>
        <Input id={`${idPrefix}-amount`} name="amount" placeholder="Amount" required />
      </div>
      {withReason && <Input id={`${idPrefix}-reason`} name="reason" placeholder="Reason" required />}
      <ModeSelect id={`${idPrefix}-mode`} />
      <Button type="submit" size="sm" variant="outline">
        {label}
      </Button>
    </form>
  );
}
