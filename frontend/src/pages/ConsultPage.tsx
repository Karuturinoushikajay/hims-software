import { useQuery } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Doctor = { id: string; name: string; consultation_fee: string; department: string };
type PatientSummary = {
  id: string;
  uhid: string;
  full_name: string;
  gender: string;
  age_years: number | null;
  mobile: string;
  registration?: { expires_on: string } | null;
};
type Result = {
  id: string;
  visit_no: string;
  patient_id: string;
  fee_waived_reason: string;
  bill: { bill_no: string; net_amount: string; due_amount: string; status: string } | null;
};

export function ConsultPage() {
  const [params] = useSearchParams();
  const patientId = params.get("patient") || "";
  const { data } = useQuery({
    queryKey: ["lookups"],
    queryFn: () => api<{ doctors: Doctor[] }>("/opd/lookups"),
  });
  const patientQuery = useQuery({
    queryKey: ["patient", patientId],
    queryFn: () => api<PatientSummary>(`/patients/${patientId}`),
    enabled: Boolean(patientId),
    retry: false,
  });
  const patient = patientQuery.data;
  const [result, setResult] = useState<Result | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pendingDiscount, setPendingDiscount] = useState<Record<string, string> | null>(null);
  const [approvalNote, setApprovalNote] = useState<string | null>(null);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setApprovalNote(null);
    const form = new FormData(e.currentTarget);
    const body: Record<string, string> = { patient_id: patientId };
    form.forEach((value, key) => {
      if (String(value).trim()) body[key] = String(value);
    });
    try {
      setResult(await api<Result>("/opd/consultations", { method: "POST", json: body }));
      setPendingDiscount(null);
    } catch (err) {
      const failure = err as Error & { code?: string };
      if (failure.code === "discount_not_authorized") {
        setPendingDiscount(body);
      }
      setError(failure.message);
    }
  }

  async function requestApproval() {
    if (!pendingDiscount) return;
    setError(null);
    try {
      await api("/billing/discount-requests", { method: "POST", json: pendingDiscount });
      setPendingDiscount(null);
      setApprovalNote("Sent for approval. A facility admin can post it from Billing.");
    } catch (err) {
      setError((err as Error).message);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">Consultation</h1>
      <Card>
        <CardHeader>
          <CardTitle>Find, record vitals, collect</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-3" onSubmit={(e) => void onSubmit(e)}>
            <div className="md:col-span-3 rounded-md border border-slate-200 bg-slate-50 p-3 text-sm">
              {!patientId && (
                <p className="text-slate-600">No patient selected. Search for a patient by name, MR number, or mobile in the top bar.</p>
              )}
              {patientId && patientQuery.isLoading && <p className="text-slate-600">Loading patient…</p>}
              {patientId && patientQuery.isError && (
                <p className="text-red-600">Patient not found. Search again in the top bar.</p>
              )}
              {patient && (
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="font-semibold">
                      {patient.full_name} · <span className="font-mono">{patient.uhid}</span>
                    </div>
                    <div className="text-slate-600">
                      {patient.gender === "F" ? "Female" : patient.gender === "M" ? "Male" : "Other"}
                      {patient.age_years !== null && ` · ${patient.age_years} yrs`} · {patient.mobile}
                      {patient.registration && ` · Valid until ${patient.registration.expires_on}`}
                    </div>
                  </div>
                  <Link className="text-brand-700 underline" to="/register">
                    Register new patient
                  </Link>
                </div>
              )}
            </div>
            <div className="md:col-span-3">
              <Label htmlFor="doctor_id">Doctor</Label>
              <select id="doctor_id" name="doctor_id" className="h-10 w-full rounded-md border px-2 text-sm" required>
                {(data?.doctors || []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.name} · {d.department} · ₹{d.consultation_fee}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <Label htmlFor="weight_kg">Weight kg</Label>
              <Input id="weight_kg" name="weight_kg" />
            </div>
            <div>
              <Label htmlFor="bp_systolic">BP systolic</Label>
              <Input id="bp_systolic" name="bp_systolic" />
            </div>
            <div>
              <Label htmlFor="temperature_f">Temp F</Label>
              <Input id="temperature_f" name="temperature_f" />
            </div>
            <div>
              <Label htmlFor="discount_type">Discount</Label>
              <select id="discount_type" name="discount_type" className="h-10 w-full rounded-md border px-2 text-sm">
                <option value="NONE">No discount</option>
                <option value="PERCENT">Percent</option>
                <option value="FLAT">Flat</option>
              </select>
            </div>
            <div>
              <Label htmlFor="discount_value">Discount value</Label>
              <Input id="discount_value" name="discount_value" defaultValue="0" />
            </div>
            <div>
              <Label htmlFor="payment_mode">Payment</Label>
              <select id="payment_mode" name="payment_mode" className="h-10 w-full rounded-md border px-2 text-sm">
                <option value="CASH">Cash</option>
                <option value="UPI">UPI</option>
                <option value="CARD">Card</option>
              </select>
            </div>
            <div className="md:col-span-3">
              <Button type="submit" disabled={!patient}>
                Save consultation
              </Button>
            </div>
          </form>
          {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
          {pendingDiscount && (
            <Button type="button" variant="outline" className="mt-3" onClick={() => void requestApproval()}>
              Send discount for approval
            </Button>
          )}
          {approvalNote && <p className="mt-3 text-sm text-emerald-700">{approvalNote}</p>}
        </CardContent>
      </Card>
      {result && (
        <Card>
          <CardContent className="space-y-2 py-4 text-sm">
            <p>Visit {result.visit_no}</p>
            {result.fee_waived_reason ? (
              <p>Fee waived: {result.fee_waived_reason}</p>
            ) : (
              result.bill && (
                <p>
                  Bill {result.bill.bill_no} · net {result.bill.net_amount} · due {result.bill.due_amount} · {result.bill.status}
                </p>
              )
            )}
            <Link className="inline-block text-brand-700 underline" to={`/emr?patient=${result.patient_id}&visit=${result.id}`}>
              Open clinical record
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
