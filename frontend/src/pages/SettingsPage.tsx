import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, type Me } from "@/lib/api";

type Settings = {
  gstin: string;
  gstin_confirmed: boolean;
  session_timeout_minutes: number;
  refund_auth_threshold: string;
  tds_commission_rate: string;
  tds_rate_confirmed: boolean;
  letterhead_text: string;
  require_2fa_roles: string[];
};

export function SettingsPage({ me }: { me: Me }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const facilityId = me.active_facility_id;
  const { data, isLoading, error } = useQuery({
    queryKey: ["settings", facilityId],
    enabled: !!facilityId,
    queryFn: () => api<Settings>(`/facilities/${facilityId}/settings`),
  });

  const [form, setForm] = useState<Partial<Settings>>({});
  const [totpQr, setTotpQr] = useState<string | null>(null);
  const [totpToken, setTotpToken] = useState("");
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (data) setForm(data);
  }, [data]);

  const save = useMutation({
    mutationFn: () =>
      api(`/facilities/${facilityId}/settings`, {
        method: "PATCH",
        json: {
          gstin: form.gstin,
          session_timeout_minutes: form.session_timeout_minutes,
          refund_auth_threshold: form.refund_auth_threshold,
          tds_commission_rate: form.tds_commission_rate,
          letterhead_text: form.letterhead_text,
        },
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["settings", facilityId] });
      setMessage("Settings saved.");
    },
    onError: (e: Error) => setMessage(e.message),
  });

  async function setup2fa() {
    const res = await api<{ qr_png_base64: string }>("/auth/2fa/setup", { method: "POST" });
    setTotpQr(res.qr_png_base64);
  }

  async function confirm2fa(e: FormEvent) {
    e.preventDefault();
    await api("/auth/2fa/confirm", { method: "POST", json: { token: totpToken } });
    setMessage("2FA enabled.");
    setTotpQr(null);
  }

  if (!facilityId) return <p>Select a facility.</p>;
  if (isLoading) return <p>Loading…</p>;
  if (error) return <p className="text-red-600">{(error as Error).message}</p>;

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{t("settings")}</h1>
      {!data?.gstin_confirmed && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {t("unconfirmedGst")}
        </div>
      )}
      {!data?.tds_rate_confirmed && (
        <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-sm text-amber-900">
          {t("unconfirmedTds")}
        </div>
      )}
      <Card>
        <CardHeader>
          <CardTitle>Facility</CardTitle>
        </CardHeader>
        <CardContent>
          <form
            className="grid max-w-xl gap-3"
            onSubmit={(e) => {
              e.preventDefault();
              save.mutate();
            }}
          >
            <div>
              <Label htmlFor="gstin">GSTIN</Label>
              <Input
                id="gstin"
                value={form.gstin || ""}
                onChange={(e) => setForm((f) => ({ ...f, gstin: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="timeout">Session timeout (minutes)</Label>
              <Input
                id="timeout"
                type="number"
                value={form.session_timeout_minutes ?? 30}
                onChange={(e) =>
                  setForm((f) => ({ ...f, session_timeout_minutes: Number(e.target.value) }))
                }
              />
            </div>
            <div>
              <Label htmlFor="refund">Refund auth threshold (INR)</Label>
              <Input
                id="refund"
                value={form.refund_auth_threshold || ""}
                onChange={(e) => setForm((f) => ({ ...f, refund_auth_threshold: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="tds">TDS commission rate (%)</Label>
              <Input
                id="tds"
                value={form.tds_commission_rate || ""}
                onChange={(e) => setForm((f) => ({ ...f, tds_commission_rate: e.target.value }))}
              />
            </div>
            <div>
              <Label htmlFor="letterhead">Letterhead text</Label>
              <Input
                id="letterhead"
                value={form.letterhead_text || ""}
                onChange={(e) => setForm((f) => ({ ...f, letterhead_text: e.target.value }))}
              />
            </div>
            <Button type="submit" disabled={save.isPending}>
              Save
            </Button>
          </form>
          {message && <p className="mt-3 text-sm text-slate-600">{message}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Two-factor authentication</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <p className="text-sm text-slate-600">
            Status: {me.totp_enabled ? "Enabled" : "Not enabled"}
          </p>
          {!me.totp_enabled && (
            <>
              <Button type="button" variant="outline" onClick={() => void setup2fa()}>
                Enroll authenticator
              </Button>
              {totpQr && (
                <form className="space-y-2" onSubmit={(e) => void confirm2fa(e)}>
                  <img
                    src={`data:image/png;base64,${totpQr}`}
                    alt="TOTP QR code"
                    className="h-40 w-40"
                  />
                  <Label htmlFor="confirm-totp">Enter code to confirm</Label>
                  <Input
                    id="confirm-totp"
                    value={totpToken}
                    onChange={(e) => setTotpToken(e.target.value)}
                  />
                  <Button type="submit">Confirm 2FA</Button>
                </form>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
