import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Procedure = { id: string; name: string; amount: string };
type Bill = { bill_no: string; net_amount: string; status: string };

export function ProceduresPage() {
  const { data } = useQuery({
    queryKey: ["lookups"],
    queryFn: () => api<{ procedures: Procedure[] }>("/opd/lookups"),
  });
  const [patientId, setPatientId] = useState("");
  const [bill, setBill] = useState<Bill | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const form = new FormData(e.currentTarget);
    try {
      const result = await api<{ bill: Bill }>("/opd/procedures", {
        method: "POST",
        json: {
          patient_id: patientId,
          procedure_id: String(form.get("procedure_id")),
          payment_mode: String(form.get("payment_mode") || "CASH"),
        },
      });
      setBill(result.bill);
      setError(null);
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-4">
      <h1 className="text-2xl font-semibold">Procedure</h1>
      <Card>
        <CardHeader>
          <CardTitle>Walk-in procedure</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="space-y-3" onSubmit={(e) => void onSubmit(e)}>
            <div>
              <Label htmlFor="proc-patient">Patient id</Label>
              <Input id="proc-patient" value={patientId} onChange={(e) => setPatientId(e.target.value)} required autoFocus />
            </div>
            <div>
              <Label htmlFor="procedure_id">Procedure</Label>
              <select id="procedure_id" name="procedure_id" className="h-10 w-full rounded-md border px-2 text-sm" required>
                {(data?.procedures || []).map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} · ₹{p.amount}
                  </option>
                ))}
              </select>
            </div>
            <input type="hidden" name="payment_mode" value="CASH" />
            <Button type="submit">Charge and collect</Button>
          </form>
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          {bill && (
            <p className="mt-3 text-sm">
              Bill {bill.bill_no} · {bill.net_amount} · {bill.status}
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
