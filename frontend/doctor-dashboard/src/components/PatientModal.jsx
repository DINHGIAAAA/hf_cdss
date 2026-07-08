import { useMemo, useState } from "react";
import { UserRound } from "lucide-react";
import { makePatientId, slugify } from "../utils";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
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
  const { t } = useLanguage();
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
              <DialogTitle>{t("patientModal.title")}</DialogTitle>
              <DialogDescription>{conversationName}</DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <form className="space-y-5" onSubmit={submit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("patientModal.patientName")} name="fullName" onChange={update} placeholder={t("patientModal.patientNamePlaceholder")} value={form.fullName} />
            <Field label={t("patientModal.age")} name="age" onChange={update} type="number" value={form.age} />
            <label className="space-y-1.5 text-sm">
              <span className="font-medium text-foreground">{t("patientModal.sex")}</span>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
                name="sex"
                onChange={update}
                value={form.sex}
              >
                <option value="">{t("patientModal.sexUnknown")}</option>
                <option value="male">{t("patientModal.sexMale")}</option>
                <option value="female">{t("patientModal.sexFemale")}</option>
              </select>
            </label>
            <Field label={t("patientModal.weightKg")} name="weightKg" onChange={update} type="number" value={form.weightKg} />
            <Field label={t("patientModal.sbp")} name="systolicBp" onChange={update} type="number" value={form.systolicBp} />
            <Field label={t("patientModal.heartRate")} name="heartRate" onChange={update} type="number" value={form.heartRate} />
            <Field label={t("patientModal.lvef")} name="lvef" onChange={update} type="number" value={form.lvef} />
            <Field label={t("patientModal.egfr")} name="egfr" onChange={update} type="number" value={form.egfr} />
            <Field label={t("patientModal.potassium")} name="potassium" onChange={update} type="number" value={form.potassium} />
            <Field label={t("patientModal.nyha")} name="nyhaClass" onChange={update} placeholder={t("patientModal.nyhaPlaceholder")} value={form.nyhaClass} />
            <TextField label={t("patientModal.conditions")} name="conditions" onChange={update} placeholder={t("patientModal.conditionsPlaceholder")} value={form.conditions} />
            <TextField label={t("patientModal.medications")} name="medications" onChange={update} placeholder={t("patientModal.medicationsPlaceholder")} value={form.medications} />
            <TextField label={t("patientModal.allergies")} name="allergies" onChange={update} placeholder={t("patientModal.allergiesPlaceholder")} value={form.allergies} />
            <TextField label={t("patientModal.redFlags")} name="redFlags" onChange={update} placeholder={t("patientModal.redFlagsPlaceholder")} value={form.redFlags} />
          </div>

          <Button className="w-full sm:w-auto" disabled={!form.fullName.trim()} size="lg" type="submit">
            {t("patientModal.start")}
          </Button>
        </form>
      </DialogContent>
    </Dialog>
  );
}
