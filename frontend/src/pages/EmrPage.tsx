import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type PatientSummary = {
  id: string;
  uhid: string;
  full_name: string;
  gender: string;
  age_years: number | null;
  mobile: string;
};

type Drug = { id: string; code: string; name: string; schedule: string };
type Icd = { code: string; name: string };
type Template = { id: string; name: string; body: string };

type Timeline = {
  patient: { id: string; uhid: string; full_name: string; medical_history: string };
  allergies: { id: string; substance: string; reaction: string; severity: string }[];
  events: {
    visit_id: string;
    visit_no: string;
    doctor: string;
    at: string;
    vitals: { weight_kg: string; bp: string; temperature_f: string };
    note: {
      complaints: string;
      history: string;
      examination: string;
      advice: string;
      diagnoses: { name: string; icd_code: string; is_primary: boolean }[];
    } | null;
    diagnoses: { name: string; icd_code: string; is_primary: boolean }[];
    prescriptions: { id: string; items: { name: string; dose: string; frequency: string }[]; allergy_alerts: unknown[]; interaction_alerts: unknown[] }[];
    orders: { id: string; kind: string; name: string; status: string }[];
    follow_ups: { id: string; follow_up_on: string; reason: string }[];
    attachments: { id: string; description: string; url: string }[];
  }[];
};

export function EmrPage() {
  const [params, setParams] = useSearchParams();
  const patientId = params.get("patient") || "";
  const visitId = params.get("visit") || "";
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [alerts, setAlerts] = useState<{ message: string }[]>([]);

  const patientQuery = useQuery({
    queryKey: ["patient", patientId],
    queryFn: () => api<PatientSummary>(`/patients/${patientId}`),
    enabled: Boolean(patientId),
    retry: false,
  });
  const timeline = useQuery({
    queryKey: ["timeline", patientId],
    queryFn: () => api<Timeline>(`/clinical/patients/${patientId}/timeline`),
    enabled: Boolean(patientId),
  });
  const catalog = useQuery({
    queryKey: ["clinical-catalog"],
    queryFn: () => api<{ drugs: Drug[]; icd: Icd[]; templates: Template[] }>("/clinical/catalog"),
  });

  const selectedVisit = timeline.data?.events.find((e) => e.visit_id === visitId) || timeline.data?.events[0];
  const activeVisitId = visitId || selectedVisit?.visit_id || "";

  useEffect(() => {
    if (!visitId && selectedVisit) {
      setParams({ patient: patientId, visit: selectedVisit.visit_id }, { replace: true });
    }
  }, [visitId, selectedVisit, patientId, setParams]);

  const noteQuery = useQuery({
    queryKey: ["clinical-note", activeVisitId],
    queryFn: () =>
      api<{
        complaints: string;
        history: string;
        examination: string;
        advice: string;
        diagnoses: { name: string; icd_code: string; is_primary: boolean }[];
      }>(`/clinical/visits/${activeVisitId}/note`),
    enabled: Boolean(activeVisitId),
  });

  const [complaints, setComplaints] = useState("");
  const [history, setHistory] = useState("");
  const [examination, setExamination] = useState("");
  const [advice, setAdvice] = useState("");
  const [icdCode, setIcdCode] = useState("J06.9");
  const [dxName, setDxName] = useState("");
  const [drugId, setDrugId] = useState("");
  const [dose, setDose] = useState("1 tab");
  const [frequency, setFrequency] = useState("TDS");
  const [duration, setDuration] = useState("3");
  const [ackAlerts, setAckAlerts] = useState(false);
  const [allergyDrugId, setAllergyDrugId] = useState("");
  const [orderName, setOrderName] = useState("Complete blood count");
  const [orderKind, setOrderKind] = useState("LAB");
  const [followOn, setFollowOn] = useState("");
  const [followReason, setFollowReason] = useState("Review");

  useEffect(() => {
    if (noteQuery.data) {
      setComplaints(noteQuery.data.complaints || "");
      setHistory(noteQuery.data.history || "");
      setExamination(noteQuery.data.examination || "");
      setAdvice(noteQuery.data.advice || "");
      const primary = noteQuery.data.diagnoses?.[0];
      if (primary) {
        setIcdCode(primary.icd_code || "J06.9");
        setDxName(primary.name || "");
      }
    }
  }, [noteQuery.data]);

  useEffect(() => {
    if (catalog.data?.drugs[0] && !drugId) setDrugId(catalog.data.drugs[0].id);
    if (catalog.data?.drugs[0] && !allergyDrugId) setAllergyDrugId(catalog.data.drugs[0].id);
  }, [catalog.data, drugId, allergyDrugId]);

  const saveNote = useMutation({
    mutationFn: () =>
      api(`/clinical/visits/${activeVisitId}/note`, {
        method: "PUT",
        json: {
          complaints,
          history,
          examination,
          advice,
          diagnoses: [{ icd_code: icdCode, name: dxName, is_primary: true }],
        },
      }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
      void qc.invalidateQueries({ queryKey: ["clinical-note", activeVisitId] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const issueRx = useMutation({
    mutationFn: () =>
      api("/clinical/prescriptions", {
        method: "POST",
        json: {
          visit_id: activeVisitId,
          acknowledge_alerts: ackAlerts,
          items: [
            {
              drug_id: drugId,
              dose,
              frequency,
              duration_days: Number(duration) || null,
            },
          ],
          notes: advice,
        },
      }),
    onSuccess: () => {
      setError(null);
      setAlerts([]);
      setAckAlerts(false);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (e: Error & { code?: string; fields?: { alerts?: { message: string }[] } }) => {
      if (e.code === "allergy_alert" || e.code === "interaction_alert") {
        setAlerts(e.fields?.alerts || [{ message: e.message }]);
      }
      setError(e.message);
    },
  });

  const recordAllergy = useMutation({
    mutationFn: () =>
      api("/clinical/allergies", {
        method: "POST",
        json: { patient_id: patientId, drug_id: allergyDrugId, reaction: "Known allergy", severity: "SEVERE" },
      }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const placeOrder = useMutation({
    mutationFn: () =>
      api("/clinical/orders", {
        method: "POST",
        json: { visit_id: activeVisitId, kind: orderKind, name: orderName, code: orderKind === "LAB" ? "CBC" : "XRAY" },
      }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const schedule = useMutation({
    mutationFn: () =>
      api("/clinical/follow-ups", {
        method: "POST",
        json: { visit_id: activeVisitId, follow_up_on: followOn, reason: followReason },
      }),
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (e: Error) => setError(e.message),
  });

  const upload = useMutation({
    mutationFn: async (file: File) => {
      const body = new FormData();
      body.append("file", file);
      body.append("patient_id", patientId);
      if (activeVisitId) body.append("visit_id", activeVisitId);
      body.append("description", file.name);
      return api("/clinical/attachments", { method: "POST", body });
    },
    onSuccess: () => {
      setError(null);
      void qc.invalidateQueries({ queryKey: ["timeline", patientId] });
    },
    onError: (e: Error) => setError(e.message),
  });

  if (!patientId) {
    return (
      <div className="space-y-3">
        <h1 className="text-2xl font-semibold">Clinical record</h1>
        <p className="text-slate-600">Search for a patient in the top bar, then open Clinical record from the result or consultation.</p>
        <Link className="inline-flex h-10 items-center rounded-md border border-slate-300 bg-white px-4 text-sm hover:bg-slate-50" to="/consult">
          Go to consultation
        </Link>
      </div>
    );
  }

  const patient = patientQuery.data;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">Clinical record</h1>
        {activeVisitId && (
          <a className="text-sm text-brand-700 underline" href={`/api/v1/clinical/visits/${activeVisitId}/summary.pdf`} target="_blank" rel="noreferrer">
            Print summary
          </a>
        )}
      </div>

      <Card>
        <CardContent className="pt-4 text-sm">
          {patientQuery.isLoading && <p>Loading patient…</p>}
          {patient && (
            <div>
              <div className="font-semibold">
                {patient.full_name} · <span className="font-mono">{patient.uhid}</span>
              </div>
              <div className="text-slate-600">
                {patient.gender === "F" ? "Female" : patient.gender === "M" ? "Male" : "Other"}
                {patient.age_years !== null && ` · ${patient.age_years} yrs`} · {patient.mobile}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
          {error}
          {alerts.length > 0 && (
            <ul className="mt-2 list-disc pl-5">
              {alerts.map((a) => (
                <li key={a.message}>{a.message}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="grid gap-4 xl:grid-cols-[280px_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Timeline</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {(timeline.data?.allergies || []).length > 0 && (
              <div className="rounded-md bg-amber-50 p-2 text-amber-900">
                Allergies: {timeline.data?.allergies.map((a) => a.substance).join(", ")}
              </div>
            )}
            {(timeline.data?.events || []).map((event) => (
              <button
                key={event.visit_id}
                type="button"
                className={`block w-full rounded-md border px-3 py-2 text-left ${event.visit_id === activeVisitId ? "border-brand-500 bg-brand-50" : "border-slate-200"}`}
                onClick={() => setParams({ patient: patientId, visit: event.visit_id })}
              >
                <div className="font-medium">{event.visit_no}</div>
                <div className="text-slate-600">{event.doctor}</div>
                <div className="text-xs text-slate-500">{new Date(event.at).toLocaleString()}</div>
              </button>
            ))}
            {!timeline.data?.events?.length && <p className="text-slate-500">No visits yet. Record a consultation first.</p>}
          </CardContent>
        </Card>

        <div className="space-y-4">
          {activeVisitId && (
            <>
              <Card>
                <CardHeader>
                  <CardTitle>Note · {selectedVisit?.visit_no}</CardTitle>
                </CardHeader>
                <CardContent>
                  <form
                    className="grid gap-3"
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      saveNote.mutate();
                    }}
                  >
                    <div>
                      <Label htmlFor="complaints">Complaints</Label>
                      <textarea id="complaints" className="min-h-16 w-full rounded-md border px-2 py-1 text-sm" value={complaints} onChange={(e) => setComplaints(e.target.value)} />
                    </div>
                    <div>
                      <Label htmlFor="history">History</Label>
                      <textarea id="history" className="min-h-16 w-full rounded-md border px-2 py-1 text-sm" value={history} onChange={(e) => setHistory(e.target.value)} />
                    </div>
                    <div>
                      <Label htmlFor="examination">Examination</Label>
                      <textarea id="examination" className="min-h-16 w-full rounded-md border px-2 py-1 text-sm" value={examination} onChange={(e) => setExamination(e.target.value)} />
                    </div>
                    <div>
                      <Label htmlFor="advice">Advice</Label>
                      <textarea id="advice" className="min-h-16 w-full rounded-md border px-2 py-1 text-sm" value={advice} onChange={(e) => setAdvice(e.target.value)} />
                    </div>
                    <div className="grid gap-2 md:grid-cols-2">
                      <div>
                        <Label htmlFor="icd">ICD-10</Label>
                        <select id="icd" className="h-10 w-full rounded-md border px-2 text-sm" value={icdCode} onChange={(e) => setIcdCode(e.target.value)}>
                          {(catalog.data?.icd || []).map((row) => (
                            <option key={row.code} value={row.code}>
                              {row.code} — {row.name}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <Label htmlFor="dx">Diagnosis label</Label>
                        <Input id="dx" value={dxName} onChange={(e) => setDxName(e.target.value)} placeholder="Optional override" />
                      </div>
                    </div>
                    <Button type="submit">Save note</Button>
                  </form>
                </CardContent>
              </Card>

              <div className="grid gap-4 lg:grid-cols-2">
                <Card>
                  <CardHeader>
                    <CardTitle>Prescription</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <select aria-label="Drug" className="h-10 w-full rounded-md border px-2 text-sm" value={drugId} onChange={(e) => setDrugId(e.target.value)}>
                      {(catalog.data?.drugs || []).map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.name}
                        </option>
                      ))}
                    </select>
                    <Input aria-label="Dose" value={dose} onChange={(e) => setDose(e.target.value)} placeholder="Dose" />
                    <Input aria-label="Frequency" value={frequency} onChange={(e) => setFrequency(e.target.value)} placeholder="Frequency" />
                    <Input aria-label="Duration days" value={duration} onChange={(e) => setDuration(e.target.value)} placeholder="Days" />
                    {alerts.length > 0 && (
                      <label className="flex items-center gap-2 text-sm">
                        <input type="checkbox" checked={ackAlerts} onChange={(e) => setAckAlerts(e.target.checked)} />
                        Acknowledge allergy / interaction alerts
                      </label>
                    )}
                    <Button type="button" onClick={() => issueRx.mutate()}>
                      Issue prescription
                    </Button>
                    {(selectedVisit?.prescriptions || []).map((rx) => (
                      <a key={rx.id} className="block text-sm text-brand-700 underline" href={`/api/v1/clinical/prescriptions/${rx.id}.pdf`} target="_blank" rel="noreferrer">
                        Print Rx ({rx.items.map((i) => i.name).join(", ")})
                      </a>
                    ))}
                  </CardContent>
                </Card>

                <Card>
                  <CardHeader>
                    <CardTitle>Orders, follow-up, allergy</CardTitle>
                  </CardHeader>
                  <CardContent className="space-y-3">
                    <div className="flex gap-2">
                      <select aria-label="Order kind" className="h-10 rounded-md border px-2 text-sm" value={orderKind} onChange={(e) => setOrderKind(e.target.value)}>
                        <option value="LAB">Lab</option>
                        <option value="RADIOLOGY">Radiology</option>
                      </select>
                      <Input aria-label="Order name" value={orderName} onChange={(e) => setOrderName(e.target.value)} />
                      <Button type="button" variant="outline" onClick={() => placeOrder.mutate()}>
                        Order
                      </Button>
                    </div>
                    <div className="flex gap-2">
                      <Input aria-label="Follow-up date" type="date" value={followOn} onChange={(e) => setFollowOn(e.target.value)} />
                      <Input aria-label="Follow-up reason" value={followReason} onChange={(e) => setFollowReason(e.target.value)} />
                      <Button type="button" variant="outline" onClick={() => schedule.mutate()}>
                        Schedule
                      </Button>
                    </div>
                    <div className="flex gap-2">
                      <select aria-label="Allergy drug" className="h-10 flex-1 rounded-md border px-2 text-sm" value={allergyDrugId} onChange={(e) => setAllergyDrugId(e.target.value)}>
                        {(catalog.data?.drugs || []).map((d) => (
                          <option key={d.id} value={d.id}>
                            {d.name}
                          </option>
                        ))}
                      </select>
                      <Button type="button" variant="outline" onClick={() => recordAllergy.mutate()}>
                        Record allergy
                      </Button>
                    </div>
                    <div>
                      <Label htmlFor="attach">Attachment</Label>
                      <Input
                        id="attach"
                        type="file"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) upload.mutate(file);
                        }}
                      />
                    </div>
                  </CardContent>
                </Card>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
