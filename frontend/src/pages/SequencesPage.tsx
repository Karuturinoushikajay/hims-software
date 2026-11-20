import { useQuery } from "@tanstack/react-query";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api";

type Seq = {
  id: string;
  document_type: string;
  financial_year: string;
  prefix: string;
  next_value: number;
  padding: number;
  owner: string;
};

export function SequencesPage() {
  const { data, error, isLoading } = useQuery({
    queryKey: ["sequences"],
    queryFn: () =>
      api<{ organization: Seq[]; facility: Seq[] }>("/number-sequences"),
  });

  if (isLoading) return <p>Loading…</p>;
  if (error) return <p className="text-red-600">{(error as Error).message}</p>;

  const renderTable = (rows: Seq[]) => (
    <table className="w-full text-left text-sm">
      <thead>
        <tr className="border-b text-slate-500">
          <th className="py-2">Type</th>
          <th>FY</th>
          <th>Prefix</th>
          <th>Next</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id} className="border-b border-slate-100">
            <td className="py-2 font-medium">{s.document_type}</td>
            <td>{s.financial_year || "—"}</td>
            <td>
              <code>{s.prefix}</code>
            </td>
            <td>{s.next_value}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Number Sequences</h1>
      <p className="text-sm text-slate-600">
        Read-only. Allocation runs inside document transactions (gap-free).
      </p>
      <Card>
        <CardHeader>
          <CardTitle>Organization (UHID)</CardTitle>
        </CardHeader>
        <CardContent>{renderTable(data?.organization || [])}</CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Facility documents</CardTitle>
        </CardHeader>
        <CardContent>{renderTable(data?.facility || [])}</CardContent>
      </Card>
    </div>
  );
}
