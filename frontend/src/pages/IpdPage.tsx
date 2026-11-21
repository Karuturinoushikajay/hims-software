import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type PatientHit = { id: string; full_name: string; uhid: string; mobile: string };
type Doctor = { id: string; name: string };
type BedRow = {
  bed_id: string;
  code: string;
  status: string;
  ward: string;
  room: string;
  room_type: string;
  admission_id: string;
  ip_no: string;
  patient_name: string;
  flags: { mlc: boolean; vip: boolean; quarantine: boolean } | null;
};
type Board = { counts: Record<string, number>; beds: BedRow[] };
type Admission = {
  id: string;
  ip_no: string;
  patient_name: string;
  uhid: string;
  status: string;
  bed_label: string;
  doctor_name: string;
  diet: string;
  days: number;
  nursing_notes?: { note: string; recorded_at: string }[];
  doctor_orders?: { order_text: string }[];
  mar?: { drug_name: string; dose: string }[];
  discharge_summary?: { diagnosis: string } | null;
  settlement?: { open_due_total: string; advance_balance: string; estimated_payable: string };
};

type Lookups = { doctors: Doctor[] };

const SECTIONS = ["Board", "Admit", "Care", "Discharge", "Certificates"] as const;

export function IpdPage() {
  const qc = useQueryClient();
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Board");
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);
  const [patientQuery, setPatientQuery] = useState("");
  const [patientHits, setPatientHits] = useState<PatientHit[]>([]);
  const [patientId, setPatientId] = useState("");
  const [patientLabel, setPatientLabel] = useState("");
  const [doctorId, setDoctorId] = useState("");
  const [bedId, setBedId] = useState("");
  const [advance, setAdvance] = useState("2000");
  const [selectedId, setSelectedId] = useState("");
  const [nurseNote, setNurseNote] = useState("");
  const [drugName, setDrugName] = useState("Paracetamol");
  const [orderText, setOrderText] = useState("");
  const [diagnosis, setDiagnosis] = useState("");
  const [conditionOut, setConditionOut] = useState("Improved");
  const [certKind, setCertKind] = useState("FITNESS");
  const [certBody, setCertBody] = useState("Fit to resume routine activity.");

  const board = useQuery({ queryKey: ["ipd-board"], queryFn: () => api<Board>("/ipd/bed-board") });
  const admissions = useQuery({
    queryKey: ["ipd-admissions"],
    queryFn: () => api<Admission[]>("/ipd/admissions?status=ADMITTED"),
  });
  const lookups = useQuery({
    queryKey: ["opd-lookups-ipd"],
    queryFn: () => api<Lookups>("/opd/lookups"),
  });
  const detail = useQuery({
    queryKey: ["ipd-detail", selectedId],
    enabled: Boolean(selectedId),
    queryFn: () => api<Admission>(`/ipd/admissions/${selectedId}`),
  });
  const certs = useQuery({
    queryKey: ["ipd-certs"],
    queryFn: () => api<{ kinds: { value: string; label: string }[]; items: { id: string; cert_no: string; kind: string }[] }>("/ipd/certificates"),
  });

  const vacantBeds = useMemo(
    () => (board.data?.beds || []).filter((b) => b.status === "VACANT"),
    [board.data],
  );
  const activeDoctorId = doctorId || lookups.data?.doctors[0]?.id || "";
  const activeBedId = bedId || vacantBeds[0]?.bed_id || "";

  const refresh = () => {
    void qc.invalidateQueries({ queryKey: ["ipd-board"] });
    void qc.invalidateQueries({ queryKey: ["ipd-admissions"] });
    void qc.invalidateQueries({ queryKey: ["ipd-detail"] });
    void qc.invalidateQueries({ queryKey: ["ipd-certs"] });
  };

  const run = useMutation({
    mutationFn: (job: { path: string; json?: unknown; method?: string }) =>
      api(job.path, { method: job.method || "POST", json: job.json ?? {} }),
    onSuccess: (data: unknown, vars) => {
      setError(null);
      if (vars.path.endsWith("/admissions") && !vars.path.includes("/admissions/")) {
        const adm = data as Admission;
        setNote(`Admitted ${adm.ip_no}`);
        setSelectedId(adm.id);
      } else if (vars.path.includes("/settle")) {
        setNote("Discharged and settled");
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

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold">In-patient</h1>
        <div className="flex flex-wrap gap-2">
          {SECTIONS.map((s) => (
            <Button key={s} type="button" variant={section === s ? "default" : "outline"} onClick={() => setSection(s)}>
              {s}
            </Button>
          ))}
        </div>
      </div>
      {error && <p className="rounded-md bg-red-50 p-3 text-sm text-red-700">{error}</p>}
      {note && <p className="rounded-md bg-emerald-50 p-3 text-sm text-emerald-800">{note}</p>}

      {section === "Board" && (
        <Card>
          <CardHeader>
            <CardTitle>
              Bed board · vacant {board.data?.counts.VACANT || 0} · occupied {board.data?.counts.OCCUPIED || 0}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {(board.data?.beds || []).map((bed) => (
                <button
                  key={bed.bed_id}
                  type="button"
                  className={`rounded border px-3 py-2 text-left text-sm ${
                    bed.status === "OCCUPIED"
                      ? "border-amber-300 bg-amber-50"
                      : bed.status === "BLOCKED"
                        ? "border-slate-300 bg-slate-100"
                        : "border-emerald-200 bg-emerald-50"
                  }`}
                  onClick={() => {
                    if (bed.admission_id) {
                      setSelectedId(bed.admission_id);
                      setSection("Care");
                    } else {
                      setBedId(bed.bed_id);
                      setSection("Admit");
                    }
                  }}
                >
                  <div className="font-medium">
                    {bed.code} · {bed.status}
                  </div>
                  <div className="text-xs text-slate-600">
                    {bed.ward} / {bed.room} ({bed.room_type})
                  </div>
                  {bed.patient_name && (
                    <div className="mt-1 text-xs">
                      {bed.ip_no} · {bed.patient_name}
                      {bed.flags?.vip ? " · VIP" : ""}
                      {bed.flags?.mlc ? " · MLC" : ""}
                    </div>
                  )}
                </button>
              ))}
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Admit" && (
        <Card>
          <CardHeader>
            <CardTitle>Admit patient</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              className="grid max-w-xl gap-3"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                if (!patientId || !activeDoctorId || !activeBedId) {
                  setError("Patient, doctor, and vacant bed are required");
                  return;
                }
                run.mutate({
                  path: "/ipd/admissions",
                  json: {
                    patient_id: patientId,
                    doctor_id: activeDoctorId,
                    bed_id: activeBedId,
                    advance_amount: advance,
                    food_preference: "VEG",
                  },
                });
              }}
            >
              <div className="relative">
                <Label htmlFor="patient">Patient</Label>
                <Input
                  id="patient"
                  value={patientQuery}
                  placeholder="Name, MR, or mobile"
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
                          onClick={() => {
                            setPatientId(hit.id);
                            setPatientLabel(`${hit.full_name} · ${hit.uhid}`);
                            setPatientQuery(`${hit.full_name} · ${hit.uhid}`);
                            setPatientHits([]);
                          }}
                        >
                          {hit.full_name} · {hit.uhid}
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {patientLabel && <p className="mt-1 text-xs text-emerald-700">{patientLabel}</p>}
              </div>
              <div>
                <Label htmlFor="doctor">Doctor</Label>
                <select
                  id="doctor"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  value={activeDoctorId}
                  onChange={(e) => setDoctorId(e.target.value)}
                >
                  {(lookups.data?.doctors || []).map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="bed">Vacant bed</Label>
                <select
                  id="bed"
                  className="w-full rounded-md border px-3 py-2 text-sm"
                  value={activeBedId}
                  onChange={(e) => setBedId(e.target.value)}
                >
                  {vacantBeds.map((b) => (
                    <option key={b.bed_id} value={b.bed_id}>
                      {b.code} · {b.ward} / {b.room}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor="adv">Advance</Label>
                <Input id="adv" value={advance} onChange={(e) => setAdvance(e.target.value)} />
              </div>
              <Button type="submit" disabled={run.isPending || !patientId}>
                Admit & take advance
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      {section === "Care" && (
        <div className="grid gap-4 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>Active admissions</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {(admissions.data || []).map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={`block w-full rounded border px-3 py-2 text-left ${selectedId === a.id ? "bg-brand-50" : ""}`}
                  onClick={() => setSelectedId(a.id)}
                >
                  {a.ip_no} · {a.patient_name}
                  <div className="text-xs text-slate-500">
                    {a.bed_label} · {a.doctor_name}
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{detail.data ? `${detail.data.ip_no} care` : "Select an admission"}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {detail.data && (
                <>
                  <p className="text-sm text-slate-600">
                    Diet: {detail.data.diet || "—"} · Day {detail.data.days}
                  </p>
                  <form
                    className="space-y-2"
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      run.mutate({
                        path: `/ipd/admissions/${detail.data!.id}/nursing-notes`,
                        json: { note: nurseNote, diet: nurseNote ? detail.data!.diet : undefined },
                      });
                      setNurseNote("");
                    }}
                  >
                    <Label>Nursing note</Label>
                    <Input value={nurseNote} onChange={(e) => setNurseNote(e.target.value)} />
                    <Button type="submit" variant="outline">
                      Save note
                    </Button>
                  </form>
                  <form
                    className="space-y-2"
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      run.mutate({
                        path: `/ipd/admissions/${detail.data!.id}/mar`,
                        json: { drug_name: drugName, dose: "1 tab", route: "PO" },
                      });
                    }}
                  >
                    <Label>MAR drug</Label>
                    <Input value={drugName} onChange={(e) => setDrugName(e.target.value)} />
                    <Button type="submit" variant="outline">
                      Record dose
                    </Button>
                  </form>
                  <form
                    className="space-y-2"
                    onSubmit={(e: FormEvent) => {
                      e.preventDefault();
                      run.mutate({
                        path: `/ipd/admissions/${detail.data!.id}/doctor-orders`,
                        json: { order_text: orderText },
                      });
                      setOrderText("");
                    }}
                  >
                    <Label>Doctor order</Label>
                    <Input value={orderText} onChange={(e) => setOrderText(e.target.value)} />
                    <Button type="submit" variant="outline">
                      Add order
                    </Button>
                  </form>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {section === "Discharge" && (
        <Card>
          <CardHeader>
            <CardTitle>Discharge & settlement</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <select
              className="w-full max-w-lg rounded-md border px-3 py-2 text-sm"
              value={selectedId}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              <option value="">Select admission</option>
              {(admissions.data || []).map((a) => (
                <option key={a.id} value={a.id}>
                  {a.ip_no} · {a.patient_name}
                </option>
              ))}
            </select>
            <div>
              <Label>Diagnosis</Label>
              <Input value={diagnosis} onChange={(e) => setDiagnosis(e.target.value)} />
            </div>
            <div>
              <Label>Condition on discharge</Label>
              <Input value={conditionOut} onChange={(e) => setConditionOut(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button
                type="button"
                variant="outline"
                disabled={!selectedId}
                onClick={() =>
                  run.mutate({
                    path: `/ipd/admissions/${selectedId}/discharge-summary`,
                    json: {
                      diagnosis,
                      condition_on_discharge: conditionOut,
                      condition_on_admission: "As admitted",
                      treatment_given: "As per IP chart",
                      treatment_advised: "Follow up",
                    },
                  })
                }
              >
                Save summary
              </Button>
              <Button
                type="button"
                disabled={!selectedId || run.isPending}
                onClick={() => run.mutate({ path: `/ipd/admissions/${selectedId}/settle`, json: {} })}
              >
                Settle & discharge
              </Button>
              {selectedId && (
                <a
                  className="inline-flex items-center text-sm text-brand-700 underline"
                  href={`/api/v1/ipd/admissions/${selectedId}/discharge.pdf`}
                  target="_blank"
                  rel="noreferrer"
                >
                  PDF
                </a>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {section === "Certificates" && (
        <Card>
          <CardHeader>
            <CardTitle>Medical certificates</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <form
              className="grid max-w-lg gap-2"
              onSubmit={(e: FormEvent) => {
                e.preventDefault();
                if (!selectedId) {
                  setError("Select an admission from Discharge/Care first");
                  return;
                }
                run.mutate({
                  path: "/ipd/certificates",
                  json: {
                    admission_id: selectedId,
                    kind: certKind,
                    disease_name: diagnosis || "As per records",
                    body: certBody,
                    fit_on: new Date().toISOString().slice(0, 10),
                  },
                });
              }}
            >
              <Label>Type</Label>
              <select
                className="rounded-md border px-3 py-2 text-sm"
                value={certKind}
                onChange={(e) => setCertKind(e.target.value)}
              >
                {(certs.data?.kinds || []).map((k) => (
                  <option key={k.value} value={k.value}>
                    {k.label}
                  </option>
                ))}
              </select>
              <Label>Body</Label>
              <Input value={certBody} onChange={(e) => setCertBody(e.target.value)} />
              <Button type="submit">Issue certificate</Button>
            </form>
            <ul className="space-y-1 text-sm">
              {(certs.data?.items || []).map((c) => (
                <li key={c.id}>
                  <a className="text-brand-700 underline" href={`/api/v1/ipd/certificates/${c.id}/pdf`} target="_blank" rel="noreferrer">
                    {c.cert_no} · {c.kind}
                  </a>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
