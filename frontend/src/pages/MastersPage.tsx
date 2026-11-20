import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, ReactNode, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api } from "@/lib/api";

type Row = Record<string, string | number | boolean | Row[] | undefined>;

type Catalog = {
  departments: Row[];
  specializations: Row[];
  doctors: Row[];
  referrals: Row[];
  pros: Row[];
  parties: Row[];
  procedures: Row[];
  services: Row[];
  room_types: Row[];
  wards: Row[];
  tariffs: Row[];
  discount_rules: Row[];
  payment_modes: Row[];
  taxes: Row[];
  templates: Row[];
  countries: Row[];
  states: Row[];
  cities: Row[];
  areas: Row[];
};

const SECTIONS = [
  "Departments",
  "Doctors",
  "Services",
  "Procedures",
  "Wards and beds",
  "Tariffs",
  "Taxes",
  "Discounts",
  "Payment modes",
  "Templates",
  "Geography",
  "Referrals",
] as const;

function text(row: Row, key: string) {
  const value = row[key];
  return value === undefined || value === null ? "" : String(value);
}

export function MastersPage() {
  const qc = useQueryClient();
  const { data, error } = useQuery({
    queryKey: ["masters"],
    queryFn: () => api<Catalog>("/masters"),
  });
  const [section, setSection] = useState<(typeof SECTIONS)[number]>("Departments");
  const [formError, setFormError] = useState<string | null>(null);

  const save = useMutation({
    mutationFn: (job: { path: string; json: unknown; method?: string }) =>
      api(job.path, { method: job.method || "POST", json: job.json }),
    onSuccess: () => {
      setFormError(null);
      void qc.invalidateQueries({ queryKey: ["masters"] });
    },
    onError: (e: Error) => setFormError(e.message),
  });

  function onSubmit(event: FormEvent, path: string, json: unknown, method?: string) {
    event.preventDefault();
    save.mutate({ path, json, method });
  }

  if (error) {
    return (
      <div className="rounded-md border border-red-200 bg-red-50 p-4 text-red-700" role="alert">
        {(error as Error).message}
      </div>
    );
  }
  if (!data) return <p>Loading masters…</p>;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-2xl font-semibold">Masters</h1>
        <label className="text-sm text-slate-600">
          Section
          <select
            className="ml-2 h-9 rounded-md border border-slate-300 px-2"
            value={section}
            onChange={(e) => {
              setSection(e.target.value as (typeof SECTIONS)[number]);
              setFormError(null);
            }}
          >
            {SECTIONS.map((name) => (
              <option key={name}>{name}</option>
            ))}
          </select>
        </label>
      </div>
      {formError && (
        <div className="rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700" role="alert">
          {formError}
        </div>
      )}
      {section === "Departments" && (
        <Section title="Departments" rows={data.departments.map((r) => [text(r, "name"), text(r, "is_active")])}>
          <NameForm
            label="Department"
            onSubmit={(e, name) => onSubmit(e, "/masters/departments", { name })}
          />
        </Section>
      )}
      {section === "Doctors" && <Doctors data={data} onSubmit={onSubmit} />}
      {section === "Services" && <Services data={data} onSubmit={onSubmit} />}
      {section === "Procedures" && (
        <Section
          title="Procedures"
          rows={data.procedures.map((r) => [text(r, "code"), text(r, "name"), text(r, "amount")])}
        >
          <ChargeForm
            onSubmit={(e, body) => onSubmit(e, "/masters/procedures", body)}
          />
        </Section>
      )}
      {section === "Wards and beds" && <Wards data={data} onSubmit={onSubmit} />}
      {section === "Tariffs" && <Tariffs data={data} onSubmit={onSubmit} />}
      {section === "Taxes" && (
        <Section
          title="Tax categories"
          rows={data.taxes.map((r) => [text(r, "name"), text(r, "hsn_sac"), `${text(r, "rate_percent")}%`])}
        >
          <TaxForm onSubmit={(e, body) => onSubmit(e, "/masters/taxes", body)} />
        </Section>
      )}
      {section === "Discounts" && (
        <Section
          title="Discount rules"
          rows={data.discount_rules.map((r) => [
            text(r, "name"),
            `${text(r, "max_percent")}%`,
            text(r, "max_flat"),
            text(r, "is_active"),
          ])}
        >
          <p className="text-sm text-slate-600">
            The strictest active rule is the facility ceiling. A role can still be tighter.
          </p>
          <DiscountForm onSubmit={(e, body) => onSubmit(e, "/masters/discount-rules", body)} />
        </Section>
      )}
      {section === "Payment modes" && (
        <Card>
          <CardHeader>
            <CardTitle>Payment modes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {data.payment_modes.map((mode) => (
              <div key={text(mode, "id")} className="flex items-center justify-between gap-3 text-sm">
                <span>
                  {text(mode, "name")} ({text(mode, "code")})
                </span>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() =>
                    save.mutate({
                      path: `/masters/payment-modes/${text(mode, "id")}`,
                      method: "PATCH",
                      json: { is_active: !mode.is_active },
                    })
                  }
                >
                  {mode.is_active ? "Active" : "Inactive"}
                </Button>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {section === "Templates" && <Templates data={data} onSubmit={onSubmit} />}
      {section === "Geography" && <Geography data={data} onSubmit={onSubmit} />}
      {section === "Referrals" && (
        <Section
          title="Referral doctors and PROs"
          rows={[
            ...data.referrals.map((r) => ["Referral", text(r, "name"), `${text(r, "commission_percent")}%`]),
            ...data.pros.map((r) => ["PRO", text(r, "name"), `${text(r, "commission_percent")}%`]),
          ]}
        >
          <ReferralForm onSubmit={(e, body) => onSubmit(e, "/masters/referrals", body)} />
        </Section>
      )}
    </div>
  );
}

function Section({
  title,
  rows,
  children,
}: {
  title: string;
  rows: string[][];
  children: ReactNode;
}) {
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_1.2fr]">
      <Card>
        <CardHeader>
          <CardTitle>{title}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">{children}</CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Current</CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-1 text-sm">
            {rows.length === 0 && <li className="text-slate-500">None yet.</li>}
            {rows.map((cells, index) => (
              <li key={`${cells.join("-")}-${index}`} className="border-b border-slate-100 py-1">
                {cells.filter(Boolean).join(" · ")}
              </li>
            ))}
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}

function NameForm({ label, onSubmit }: { label: string; onSubmit: (e: FormEvent, name: string) => void }) {
  const [name, setName] = useState("");
  return (
    <form
      className="flex gap-2"
      onSubmit={(e) => {
        onSubmit(e, name);
        setName("");
      }}
    >
      <Input aria-label={label} placeholder={label} value={name} onChange={(e) => setName(e.target.value)} required />
      <Button type="submit">Add</Button>
    </form>
  );
}

function ChargeForm({
  onSubmit,
}: {
  onSubmit: (e: FormEvent, body: Record<string, string>) => void;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [hospital, setHospital] = useState("");
  const [doctor, setDoctor] = useState("0");
  return (
    <form
      className="grid gap-2"
      onSubmit={(e) =>
        onSubmit(e, {
          code,
          name,
          amount,
          hospital_share: hospital || amount,
          doctor_share: doctor || "0",
        })
      }
    >
      <Input aria-label="Code" placeholder="Code" value={code} onChange={(e) => setCode(e.target.value)} required />
      <Input aria-label="Name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
      <Input aria-label="Amount" placeholder="Amount" value={amount} onChange={(e) => setAmount(e.target.value)} required />
      <Input
        aria-label="Hospital share"
        placeholder="Hospital share"
        value={hospital}
        onChange={(e) => setHospital(e.target.value)}
      />
      <Input
        aria-label="Doctor share"
        placeholder="Doctor share"
        value={doctor}
        onChange={(e) => setDoctor(e.target.value)}
      />
      <Button type="submit">Add</Button>
    </form>
  );
}

function Doctors({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [departmentId, setDepartmentId] = useState(text(data.departments[0] || {}, "id"));
  const specs = data.specializations.filter((s) => text(s, "department_id") === departmentId);
  const [specId, setSpecId] = useState(text(specs[0] || {}, "id"));
  const [fee, setFee] = useState("500");
  const [hospital, setHospital] = useState("300");
  const [doctorShare, setDoctorShare] = useState("200");
  const [specName, setSpecName] = useState("");
  return (
    <Section
      title="Doctors"
      rows={data.doctors.map((r) => [text(r, "code"), text(r, "name"), text(r, "consultation_fee")])}
    >
      <form
        className="grid gap-2"
        onSubmit={(e) =>
          onSubmit(e, "/masters/specializations", { name: specName, department_id: departmentId })
        }
      >
        <Label htmlFor="spec-name">Specialization</Label>
        <div className="flex gap-2">
          <Input id="spec-name" value={specName} onChange={(e) => setSpecName(e.target.value)} placeholder="New specialization" />
          <Button type="submit" variant="outline">
            Add
          </Button>
        </div>
      </form>
      <form
        className="grid gap-2"
        onSubmit={(e) =>
          onSubmit(e, "/masters/doctors", {
            code,
            name,
            department_id: departmentId,
            specialization_id: specId,
            consultation_fee: fee,
            hospital_share: hospital,
            doctor_share: doctorShare,
          })
        }
      >
        <Input aria-label="Doctor code" placeholder="Code" value={code} onChange={(e) => setCode(e.target.value)} required />
        <Input aria-label="Doctor name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <select
          aria-label="Department"
          className="h-9 rounded-md border px-2 text-sm"
          value={departmentId}
          onChange={(e) => setDepartmentId(e.target.value)}
        >
          {data.departments.map((d) => (
            <option key={text(d, "id")} value={text(d, "id")}>
              {text(d, "name")}
            </option>
          ))}
        </select>
        <select
          aria-label="Specialization"
          className="h-9 rounded-md border px-2 text-sm"
          value={specId}
          onChange={(e) => setSpecId(e.target.value)}
        >
          {specs.map((s) => (
            <option key={text(s, "id")} value={text(s, "id")}>
              {text(s, "name")}
            </option>
          ))}
        </select>
        <Input aria-label="Consultation fee" value={fee} onChange={(e) => setFee(e.target.value)} />
        <Input aria-label="Hospital share" value={hospital} onChange={(e) => setHospital(e.target.value)} />
        <Input aria-label="Doctor share" value={doctorShare} onChange={(e) => setDoctorShare(e.target.value)} />
        <Button type="submit">Add doctor</Button>
      </form>
      <ScheduleForm doctors={data.doctors} onSubmit={onSubmit} />
    </Section>
  );
}

function ScheduleForm({
  doctors,
  onSubmit,
}: {
  doctors: Row[];
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [doctorId, setDoctorId] = useState(text(doctors[0] || {}, "id"));
  const [weekday, setWeekday] = useState("0");
  const [start, setStart] = useState("09:00");
  const [end, setEnd] = useState("13:00");
  return (
    <form
      className="grid gap-2 border-t border-slate-100 pt-3"
      onSubmit={(e) =>
        onSubmit(e, "/masters/schedules", {
          doctor_id: doctorId,
          weekday: Number(weekday),
          start_time: start,
          end_time: end,
          slot_minutes: 15,
        })
      }
    >
      <Label>Clinic hours</Label>
      <select aria-label="Doctor for schedule" className="h-9 rounded-md border px-2 text-sm" value={doctorId} onChange={(e) => setDoctorId(e.target.value)}>
        {doctors.map((d) => (
          <option key={text(d, "id")} value={text(d, "id")}>{text(d, "name")}</option>
        ))}
      </select>
      <select aria-label="Weekday" className="h-9 rounded-md border px-2 text-sm" value={weekday} onChange={(e) => setWeekday(e.target.value)}>
        {["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"].map((day, index) => (
          <option key={day} value={index}>{day}</option>
        ))}
      </select>
      <Input aria-label="Start time" type="time" value={start} onChange={(e) => setStart(e.target.value)} />
      <Input aria-label="End time" type="time" value={end} onChange={(e) => setEnd(e.target.value)} />
      <Button type="submit" variant="outline">Save hours</Button>
    </form>
  );
}

function Services({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [body, setBody] = useState({
    code: "",
    name: "",
    service_type: "GENERAL",
    charge_unit: "DAILY",
    amount: "",
    hospital_share: "",
    doctor_share: "0",
  });
  return (
    <Section
      title="Services"
      rows={data.services.map((r) => [text(r, "code"), text(r, "name"), text(r, "service_type"), text(r, "amount")])}
    >
      <form
        className="grid gap-2"
        onSubmit={(e) =>
          onSubmit(e, "/masters/services", {
            ...body,
            hospital_share: body.hospital_share || body.amount,
          })
        }
      >
        <Input aria-label="Service code" placeholder="Code" value={body.code} onChange={(e) => setBody({ ...body, code: e.target.value })} required />
        <Input aria-label="Service name" placeholder="Name" value={body.name} onChange={(e) => setBody({ ...body, name: e.target.value })} required />
        <select
          aria-label="Service type"
          className="h-9 rounded-md border px-2 text-sm"
          value={body.service_type}
          onChange={(e) => setBody({ ...body, service_type: e.target.value })}
        >
          <option value="DOCTOR">Doctor service</option>
          <option value="ROOM">Room service</option>
          <option value="GENERAL">General service</option>
        </select>
        <select
          aria-label="Charge unit"
          className="h-9 rounded-md border px-2 text-sm"
          value={body.charge_unit}
          onChange={(e) => setBody({ ...body, charge_unit: e.target.value })}
        >
          <option value="HOURLY">Hourly</option>
          <option value="DAILY">Daily</option>
          <option value="PACKAGE">Package</option>
          <option value="UNIT">Unit</option>
        </select>
        <Input aria-label="Service amount" placeholder="Amount" value={body.amount} onChange={(e) => setBody({ ...body, amount: e.target.value })} required />
        <Button type="submit">Add service</Button>
      </form>
    </Section>
  );
}

function Wards({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [typeId, setTypeId] = useState(text(data.room_types[0] || {}, "id"));
  const [wardName, setWardName] = useState("");
  const [wardId, setWardId] = useState(text(data.wards[0] || {}, "id"));
  const [roomName, setRoomName] = useState("");
  const rooms = ((data.wards.find((w) => text(w, "id") === wardId)?.rooms as Row[]) || []);
  const [roomId, setRoomId] = useState(text(rooms[0] || {}, "id"));
  const [bedCode, setBedCode] = useState("");
  const rows = data.wards.flatMap((ward) =>
    ((ward.rooms as Row[]) || []).flatMap((room) =>
      ((room.beds as Row[]) || []).map((bed) => [text(ward, "name"), text(room, "name"), text(bed, "code"), text(bed, "status")]),
    ),
  );
  return (
    <Section title="Wards, rooms, and beds" rows={rows}>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/wards", { name: wardName, room_type_id: typeId })}>
        <select aria-label="Room type" className="h-9 rounded-md border px-2 text-sm" value={typeId} onChange={(e) => setTypeId(e.target.value)}>
          {data.room_types.map((t) => (
            <option key={text(t, "id")} value={text(t, "id")}>{text(t, "name")}</option>
          ))}
        </select>
        <Input aria-label="Ward name" placeholder="Ward" value={wardName} onChange={(e) => setWardName(e.target.value)} required />
        <Button type="submit">Add ward</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/rooms", { ward_id: wardId, name: roomName })}>
        <select aria-label="Ward" className="h-9 rounded-md border px-2 text-sm" value={wardId} onChange={(e) => setWardId(e.target.value)}>
          {data.wards.map((w) => (
            <option key={text(w, "id")} value={text(w, "id")}>{text(w, "name")}</option>
          ))}
        </select>
        <Input aria-label="Room name" placeholder="Room" value={roomName} onChange={(e) => setRoomName(e.target.value)} required />
        <Button type="submit">Add room</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/beds", { room_id: roomId, code: bedCode })}>
        <select aria-label="Room" className="h-9 rounded-md border px-2 text-sm" value={roomId} onChange={(e) => setRoomId(e.target.value)}>
          {rooms.map((room) => (
            <option key={text(room, "id")} value={text(room, "id")}>{text(room, "name")}</option>
          ))}
        </select>
        <Input aria-label="Bed code" placeholder="Bed code" value={bedCode} onChange={(e) => setBedCode(e.target.value)} required />
        <Button type="submit">Add bed</Button>
      </form>
    </Section>
  );
}

function Tariffs({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [percent, setPercent] = useState("10");
  const [direction, setDirection] = useState("UP");
  const [kind, setKind] = useState("PROCEDURE");
  const [partyId, setPartyId] = useState(text(data.parties[0] || {}, "id"));
  return (
    <Section
      title="Tariffs"
      rows={data.tariffs.map((r) => [text(r, "party"), text(r, "procedure") || text(r, "service"), text(r, "amount")])}
    >
      <form
        className="grid gap-2"
        onSubmit={(e) => onSubmit(e, "/masters/tariffs/adjust", { percent, direction, kind })}
      >
        <p className="text-sm text-slate-600">
          Raises or lowers hospital and doctor shares together, so they still add up to the charge.
        </p>
        <Input aria-label="Percent" value={percent} onChange={(e) => setPercent(e.target.value)} />
        <select aria-label="Direction" className="h-9 rounded-md border px-2 text-sm" value={direction} onChange={(e) => setDirection(e.target.value)}>
          <option value="UP">Increase</option>
          <option value="DOWN">Decrease</option>
        </select>
        <select aria-label="Charge kind" className="h-9 rounded-md border px-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="PROCEDURE">Procedures</option>
          <option value="SERVICE">Services</option>
          <option value="DOCTOR">Consultation fees</option>
          <option value="ALL">All</option>
        </select>
        <Button type="submit">Apply percent</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/tariffs/copy", { party_id: partyId })}>
        <select aria-label="Organization" className="h-9 flex-1 rounded-md border px-2 text-sm" value={partyId} onChange={(e) => setPartyId(e.target.value)}>
          {data.parties.map((p) => (
            <option key={text(p, "id")} value={text(p, "id")}>{text(p, "name")}</option>
          ))}
        </select>
        <Button type="submit" variant="outline">Copy hospital charges</Button>
      </form>
      <PartyForm onSubmit={onSubmit} />
    </Section>
  );
}

function PartyForm({ onSubmit }: { onSubmit: (e: FormEvent, path: string, json: unknown) => void }) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState("TPA");
  return (
    <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/parties", { name, kind })}>
      <select aria-label="Organization kind" className="h-9 rounded-md border px-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
        <option value="CORPORATE">Corporate</option>
        <option value="TPA">TPA / insurer</option>
      </select>
      <Input aria-label="Organization name" placeholder="Organization" value={name} onChange={(e) => setName(e.target.value)} required />
      <Button type="submit" variant="outline">Add</Button>
    </form>
  );
}

function TaxForm({ onSubmit }: { onSubmit: (e: FormEvent, body: Record<string, string>) => void }) {
  const [name, setName] = useState("");
  const [hsn, setHsn] = useState("");
  const [rate, setRate] = useState("18");
  return (
    <form className="grid gap-2" onSubmit={(e) => onSubmit(e, { name, hsn_sac: hsn, rate_percent: rate })}>
      <Input aria-label="Tax name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
      <Input aria-label="HSN or SAC" placeholder="HSN/SAC" value={hsn} onChange={(e) => setHsn(e.target.value)} />
      <Input aria-label="Rate percent" placeholder="Rate %" value={rate} onChange={(e) => setRate(e.target.value)} required />
      <Button type="submit">Add tax</Button>
    </form>
  );
}

function DiscountForm({ onSubmit }: { onSubmit: (e: FormEvent, body: Record<string, string>) => void }) {
  const [name, setName] = useState("");
  const [percent, setPercent] = useState("10");
  const [flat, setFlat] = useState("500");
  return (
    <form className="grid gap-2" onSubmit={(e) => onSubmit(e, { name, max_percent: percent, max_flat: flat })}>
      <Input aria-label="Rule name" placeholder="Rule name" value={name} onChange={(e) => setName(e.target.value)} required />
      <Input aria-label="Max percent" placeholder="Max percent" value={percent} onChange={(e) => setPercent(e.target.value)} />
      <Input aria-label="Max flat amount" placeholder="Max flat amount" value={flat} onChange={(e) => setFlat(e.target.value)} />
      <Button type="submit">Add rule</Button>
    </form>
  );
}

function Templates({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [kind, setKind] = useState("PRESCRIPTION");
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  return (
    <Section title="Templates" rows={data.templates.map((r) => [text(r, "kind"), text(r, "name")])}>
      <form className="grid gap-2" onSubmit={(e) => onSubmit(e, "/masters/templates", { kind, name, body })}>
        <select aria-label="Template kind" className="h-9 rounded-md border px-2 text-sm" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="PRESCRIPTION">Prescription</option>
          <option value="DISCHARGE">Discharge</option>
          <option value="CERTIFICATE">Certificate</option>
        </select>
        <Input aria-label="Template name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
        <textarea
          aria-label="Template body"
          className="min-h-24 rounded-md border px-2 py-1 text-sm"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <Button type="submit">Add template</Button>
      </form>
    </Section>
  );
}

function Geography({
  data,
  onSubmit,
}: {
  data: Catalog;
  onSubmit: (e: FormEvent, path: string, json: unknown) => void;
}) {
  const [country, setCountry] = useState("");
  const [countryId, setCountryId] = useState(text(data.countries[0] || {}, "id"));
  const [stateName, setStateName] = useState("");
  const [stateId, setStateId] = useState(text(data.states[0] || {}, "id"));
  const [cityName, setCityName] = useState("");
  const [cityId, setCityId] = useState(text(data.cities[0] || {}, "id"));
  const [area, setArea] = useState("");
  return (
    <Section
      title="Geography"
      rows={data.areas.map((r) => [text(r, "country"), text(r, "state"), text(r, "city"), text(r, "name")])}
    >
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/countries", { name: country })}>
        <Input aria-label="Country" placeholder="Country" value={country} onChange={(e) => setCountry(e.target.value)} required />
        <Button type="submit">Add</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/states", { country_id: countryId, name: stateName })}>
        <select aria-label="Country for state" className="h-9 rounded-md border px-2 text-sm" value={countryId} onChange={(e) => setCountryId(e.target.value)}>
          {data.countries.map((c) => (
            <option key={text(c, "id")} value={text(c, "id")}>{text(c, "name")}</option>
          ))}
        </select>
        <Input aria-label="State" placeholder="State" value={stateName} onChange={(e) => setStateName(e.target.value)} required />
        <Button type="submit">Add</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/cities", { state_id: stateId, name: cityName })}>
        <select aria-label="State for city" className="h-9 rounded-md border px-2 text-sm" value={stateId} onChange={(e) => setStateId(e.target.value)}>
          {data.states.map((s) => (
            <option key={text(s, "id")} value={text(s, "id")}>{text(s, "name")}</option>
          ))}
        </select>
        <Input aria-label="City" placeholder="City" value={cityName} onChange={(e) => setCityName(e.target.value)} required />
        <Button type="submit">Add</Button>
      </form>
      <form className="flex gap-2" onSubmit={(e) => onSubmit(e, "/masters/areas", { city_id: cityId, name: area })}>
        <select aria-label="City for area" className="h-9 rounded-md border px-2 text-sm" value={cityId} onChange={(e) => setCityId(e.target.value)}>
          {data.cities.map((c) => (
            <option key={text(c, "id")} value={text(c, "id")}>{text(c, "name")}</option>
          ))}
        </select>
        <Input aria-label="Area" placeholder="Area" value={area} onChange={(e) => setArea(e.target.value)} required />
        <Button type="submit">Add</Button>
      </form>
    </Section>
  );
}

function ReferralForm({ onSubmit }: { onSubmit: (e: FormEvent, body: Record<string, string>) => void }) {
  const [name, setName] = useState("");
  const [hospital, setHospital] = useState("");
  const [percent, setPercent] = useState("0");
  return (
    <form className="grid gap-2" onSubmit={(e) => onSubmit(e, { name, hospital, commission_percent: percent })}>
      <Input aria-label="Referral name" placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} required />
      <Input aria-label="Hospital or clinic" placeholder="Hospital or clinic" value={hospital} onChange={(e) => setHospital(e.target.value)} />
      <Input aria-label="Commission percent" placeholder="Commission %" value={percent} onChange={(e) => setPercent(e.target.value)} />
      <Button type="submit">Add referral</Button>
    </form>
  );
}
