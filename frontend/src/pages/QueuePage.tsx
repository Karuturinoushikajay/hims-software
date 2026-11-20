import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Doctor = { id: string; name: string };
type Hit = { id: string; full_name: string; uhid: string };
type Appt = { id: string; token: number; status: string; source: string; patient_name: string; uhid: string; reminder_status: string };

export function QueuePage() {
  const qc = useQueryClient();
  const { data: lookups } = useQuery({
    queryKey: ["lookups"],
    queryFn: () => api<{ doctors: Doctor[] }>("/opd/lookups"),
  });
  const [doctorId, setDoctorId] = useState("");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<Hit[]>([]);
  const [patientId, setPatientId] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  const { data: queue } = useQuery({
    queryKey: ["queue", doctorId],
    enabled: !!doctorId,
    queryFn: () => api<Appt[]>(`/opd/appointments?doctor=${doctorId}`),
  });

  async function book(e: FormEvent) {
    e.preventDefault();
    const created = await api<Appt>("/opd/appointments", {
      method: "POST",
      json: { patient_id: patientId, doctor_id: doctorId, source: "WALKIN" },
    });
    setMessage(`Token ${created.token} for ${created.patient_name}. Reminder: ${created.reminder_status}.`);
    void qc.invalidateQueries({ queryKey: ["queue", doctorId] });
  }

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Token queue</h1>
      <Card>
        <CardHeader>
          <CardTitle>Walk-in</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-2" onSubmit={(e) => void book(e)}>
            <select
              aria-label="Doctor"
              className="h-10 rounded-md border px-2 text-sm"
              value={doctorId}
              onChange={(e) => setDoctorId(e.target.value)}
              required
            >
              <option value="">Doctor</option>
              {(lookups?.doctors || []).map((d) => (
                <option key={d.id} value={d.id}>
                  {d.name}
                </option>
              ))}
            </select>
            <div className="relative">
              <input
                aria-label="Patient"
                className="h-10 w-full rounded-md border px-3 text-sm"
                placeholder="Find patient"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  void api<Hit[]>(`/patients/search?q=${encodeURIComponent(e.target.value)}`)
                    .then(setHits)
                    .catch(() => setHits([]));
                }}
              />
              {hits.length > 0 && (
                <ul className="absolute z-10 mt-1 w-full rounded-md border bg-white shadow">
                  {hits.map((h) => (
                    <li key={h.id}>
                      <button
                        type="button"
                        className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-50"
                        onClick={() => {
                          setPatientId(h.id);
                          setQuery(`${h.full_name} (${h.uhid})`);
                          setHits([]);
                        }}
                      >
                        {h.full_name} · {h.uhid}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <Button type="submit" disabled={!patientId || !doctorId}>
              Issue token
            </Button>
          </form>
          {message && <p className="mt-3 text-sm">{message}</p>}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Today</CardTitle>
        </CardHeader>
        <CardContent>
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-slate-500">
                <th className="py-2">Token</th>
                <th>Patient</th>
                <th>Status</th>
                <th>Source</th>
              </tr>
            </thead>
            <tbody>
              {(queue || []).map((row) => (
                <tr key={row.id} className="border-t">
                  <td className="py-2 font-medium">{row.token}</td>
                  <td>
                    {row.patient_name} · {row.uhid}
                  </td>
                  <td>{row.status}</td>
                  <td>{row.source}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
