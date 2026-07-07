import { useMemo, useState } from "react";
import { UserRound } from "lucide-react";
import { makePatientId, slugify } from "../utils";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";

const EMPTY_PATIENT = {
  fullName: "",
  age: "",
  sex: "",
  weightKg: "",
  systolicBp: "",
  heartRate: "",
  lvef: "",
  egfr: "",
  potassium: "",
  nyhaClass: "",
  conditions: "",
  medications: "",
  allergies: "no known drug allergies",
  redFlags: "stable",
};

function Field({ label, name, value, onChange, type = "text", placeholder = "" }) {
  return (
    <label className="space-y-1.5 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      <Input name={name} onChange={onChange} placeholder={placeholder} type={type} value={value} />
    </label>
  );
}

function TextField({ label, name, value, onChange, placeholder = "" }) {
  return (
    <label className="col-span-full space-y-1.5 text-sm">
      <span className="font-medium text-foreground">{label}</span>
      <Textarea name={name} onChange={onChange} placeholder={placeholder} rows={2} value={value} />
    </label>
  );
}

export function PatientModal({ onCreate, onClose }) {
  const [form, setForm] = useState(EMPTY_PATIENT);
  const patientId = useMemo(() => makePatientId(form.fullName), [form.fullName]);
  const conversationName = `${slugify(form.fullName)}_${patientId.split("_").at(-1)}`;

  function update(e) {
    const { name, value } = e.target;
    setForm((cur) => ({ ...cur, [name]: value }));
  }

  function submit(e) {
    e.preventDefault();
    if (!form.fullName.trim()) return;
    onCreate(form, patientId, conversationName);
  }

  return (
    <Dialog onOpenChange={(open) => { if (!open && onClose) onClose(); }} open>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto sm:max-w-3xl" showCloseButton={Boolean(onClose)}>
        <DialogHeader>
          <div className="flex items-start gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary/10 text-primary">
              <UserRound size={20} />
            </div>
            <div>
              <DialogTitle>New Conversation</DialogTitle>
              <DialogDescription>{conversationName}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form className="space-y-5" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Patient name" name="fullName" onChange={update} placeholder="Nguyen Van A" value={form.fullName} />
            <Field label="Age" name="age" onChange={update} type="number" value={form.age} />
            <label className="space-y-1.5 text-sm">
              <span className="font-medium text-foreground">Sex</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                name="sex"
                onChange={update}
                value={form.sex}
              >
                <option value="">Unknown</option>
                <option value="male">Male</option>
                <option value="female">Female</option>
              </select>
            </label>
            <Field label="Weight kg" name="weightKg" onChange={update} type="number" value={form.weightKg} />
            <Field label="SBP mmHg" name="systolicBp" onChange={update} type="number" value={form.systolicBp} />
            <Field label="Heart rate" name="heartRate" onChange={update} type="number" value={form.heartRate} />
            <Field label="LVEF %" name="lvef" onChange={update} type="number" value={form.lvef} />
            <Field label="eGFR" name="egfr" onChange={update} type="number" value={form.egfr} />
            <Field label="K+ mmol/L" name="potassium" onChange={update} type="number" value={form.potassium} />
            <Field label="NYHA" name="nyhaClass" onChange={update} placeholder="II, III..." value={form.nyhaClass} />
            <TextField label="Conditions" name="conditions" onChange={update} placeholder="HFrEF, CKD..." value={form.conditions} />
            <TextField label="Current medications" name="medications" onChange={update} placeholder="metoprolol, furosemide..." value={form.medications} />
            <TextField label="Allergies" name="allergies" onChange={update} placeholder="penicillin, aspirin, no known drug allergies" value={form.allergies} />
            <TextField label="Red flags" name="redFlags" onChange={update} placeholder="acute decompensation, chest pain, stable" value={form.redFlags} />
          </div>

          <Button className="w-full sm:w-auto" disabled={!form.fullName.trim()} size="lg" type="submit">
            Start conversation
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
