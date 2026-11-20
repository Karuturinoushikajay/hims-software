import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type AuditRow = {
  id: string;
  created_at: string;
  action: string;
  actor: string | null;
  entity_type: string;
  entity_id: string;
  request_id: string;
};

export function AuditPage() {
  const [actor, setActor] = useState("");
  const [action, setAction] = useState("");
  const [applied, setApplied] = useState({ actor: "", action: "" });

  const { data, error, isLoading, refetch } = useQuery({
    queryKey: ["audit", applied],
    queryFn: () => {
      const params = new URLSearchParams();
      if (applied.actor) params.set("actor", applied.actor);
      if (applied.action) params.set("action", applied.action);
      const q = params.toString();
      return api<AuditRow[]>(`/audit-logs${q ? `?${q}` : ""}`);
    },
  });

  if (error) return <p className="text-red-600">{(error as Error).message}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">Audit Logs</h1>
      <Card>
        <CardHeader>
          <CardTitle>Filters</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-3">
          <div>
            <Label htmlFor="actor">Actor</Label>
            <Input id="actor" value={actor} onChange={(e) => setActor(e.target.value)} />
          </div>
          <div>
            <Label htmlFor="action">Action</Label>
            <Input id="action" value={action} onChange={(e) => setAction(e.target.value)} />
          </div>
          <Button
            type="button"
            onClick={() => {
              setApplied({ actor, action });
              void refetch();
            }}
          >
            Search
          </Button>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recent events</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <p>Loading…</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="border-b text-slate-500">
                    <th className="py-2">When</th>
                    <th>Action</th>
                    <th>Actor</th>
                    <th>Entity</th>
                    <th>Request</th>
                  </tr>
                </thead>
                <tbody>
                  {(data || []).map((row) => (
                    <tr key={row.id} className="border-b border-slate-100">
                      <td className="py-2 whitespace-nowrap">
                        {new Date(row.created_at).toLocaleString()}
                      </td>
                      <td>
                        <code>{row.action}</code>
                      </td>
                      <td>{row.actor || "—"}</td>
                      <td>
                        {row.entity_type} {row.entity_id}
                      </td>
                      <td className="font-mono text-xs">{row.request_id || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
