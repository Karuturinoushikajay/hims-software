import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Result = {
  uhid: string;
  full_name: string;
  registration?: { expires_on: string; bill: { bill_no: string; net_amount: string; receipt_no?: string; receipts: { receipt_no: string }[] } | null };
};

type RecentRow = {
  id: string;
  uhid: string;
  full_name: string;
  mobile: string;
  registration?: { registered_on: string; expires_on: string; bill: { bill_no: string } | null } | null;
};

export function RegisterPage() {
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [matches, setMatches] = useState<{ full_name: string; uhid: string }[]>([]);
  const [result, setResult] = useState<Result | null>(null);
  const [confirm, setConfirm] = useState(false);
  const { data: recent = [] } = useQuery({
    queryKey: ["patients-recent"],
    queryFn: () => api<RecentRow[]>("/patients/recent"),
  });
  
  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    const form = new FormData(e.currentTarget);
    const body: Record<string, string | boolean> = { confirm_duplicate: confirm };
    form.forEach((value, key) => {
      if (String(value).trim()) body[key] = String(value);
    });
    try {
      const created = await api<Result>("/patients/register", { method: "POST", json: body });
      setResult(created);
      setMatches([]);
      setConfirm(false);
      e.currentTarget.reset();
      void queryClient.invalidateQueries({ queryKey: ["patients-recent"] });
    } catch (err) {
      const e = err as Error & { code?: string; fields?: { matches?: { full_name: string; uhid: string }[] } };
      if (e.code === "possible_duplicate") {
        setMatches(e.fields?.matches || []);
        setConfirm(true);
        setError("A matching patient exists. Submit again to register anyway.");
      } else {
        setError(e.message);
      }
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h1 className="text-2xl font-semibold">Register patient</h1>
      <Card>
        <CardHeader>
          <CardTitle>Demographics and registration fee</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-3" onSubmit={(e) => void onSubmit(e)}>
            <div>
              <Label htmlFor="first_name">First name</Label>
              <Input id="first_name" name="first_name" autoFocus required />
            </div>
            <div>
              <Label htmlFor="last_name">Last name</Label>
              <Input id="last_name" name="last_name" />
            </div>
            <div>
              <Label htmlFor="gender">Gender</Label>
              <select id="gender" name="gender" className="h-10 w-full rounded-md border px-2 text-sm" required>
                <option value="F">Female</option>
                <option value="M">Male</option>
                <option value="O">Other</option>
              </select>
            </div>
            <div>
              <Label htmlFor="mobile">Mobile</Label>
              <Input id="mobile" name="mobile" required />
            </div>
            <div>
              <Label htmlFor="age_years">Age (years)</Label>
              <Input id="age_years" name="age_years" inputMode="numeric" />
            </div>
            <div>
              <Label htmlFor="date_of_birth">Date of birth</Label>
              <Input id="date_of_birth" name="date_of_birth" type="date" />
            </div>
            <div>
              <Label htmlFor="abha_id">ABHA ID</Label>
              <Input id="abha_id" name="abha_id" />
            </div>
            <div>
              <Label htmlFor="city">City</Label>
              <Input id="city" name="city" defaultValue="Hyderabad" />
            </div>
            <div>
              <Label htmlFor="area">Area</Label>
              <Input id="area" name="area" />
            </div>
            <div className="md:col-span-3">
              <Label htmlFor="address">Address</Label>
              <Input id="address" name="address" />
            </div>
            <div className="md:col-span-3">
              <Button type="submit">{confirm ? "Register anyway" : "Register and collect fee"}</Button>
            </div>
          </form>
          {error && <p className="mt-3 text-sm text-amber-800">{error}</p>}
          {matches.length > 0 && (
            <ul className="mt-2 text-sm text-slate-600">
              {matches.map((m) => (
                <li key={m.uhid}>
                  {m.full_name} · {m.uhid}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
      {result && (
        <Card>
          <CardHeader>
            <CardTitle>Registered</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>
              {result.full_name} · <strong>{result.uhid}</strong>
            </p>
            <p>Valid until {result.registration?.expires_on}</p>
            {result.registration?.bill && (
              <p>
                Bill {result.registration.bill.bill_no} · net {result.registration.bill.net_amount} · receipt{" "}
                {result.registration.bill.receipts[0]?.receipt_no}
              </p>
            )}
          </CardContent>
        </Card>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Recent registrations</CardTitle>
        </CardHeader>
        <CardContent className="text-sm">
          {recent.length === 0 ? (
            <p className="text-slate-500">No registrations yet at this facility.</p>
          ) : (
            <table className="w-full text-left">
              <thead className="border-b text-slate-500">
                <tr>
                  <th className="py-2 font-medium">MR number</th>
                  <th className="py-2 font-medium">Name</th>
                  <th className="py-2 font-medium">Mobile</th>
                  <th className="py-2 font-medium">Registered</th>
                  <th className="py-2 font-medium">Bill</th>
                  <th className="py-2 font-medium" />
                </tr>
              </thead>
              <tbody>
                {recent.map((row) => (
                  <tr key={row.id} className="border-b last:border-0">
                    <td className="py-2 font-mono">{row.uhid}</td>
                    <td className="py-2">{row.full_name}</td>
                    <td className="py-2">{row.mobile}</td>
                    <td className="py-2">{row.registration?.registered_on ?? "-"}</td>
                    <td className="py-2">{row.registration?.bill?.bill_no ?? "-"}</td>
                    <td className="py-2 text-right">
                      <Link className="text-brand-700 underline" to={`/consult?patient=${row.id}`}>
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
