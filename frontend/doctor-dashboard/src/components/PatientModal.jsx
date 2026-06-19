import { useMemo, useState } from "react";
import { X, UserRound } from "lucide-react";
import { makePatientId, slugify } from "../utils";

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
    <label className="field">
      <span>{label}</span>
      <input name={name} onChange={onChange} placeholder={placeholder} type={type} value={value} />
    </label>
  );
}

function TextField({ label, name, value, onChange, placeholder = "" }) {
  return (
    <label className="field wide">
      <span>{label}</span>
      <textarea name={name} onChange={onChange} placeholder={placeholder} value={value} />
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
    <div className="modal-backdrop">
      <form className="patient-modal" onSubmit={submit}>
        <div className="modal-head">
          <div>
            <h1>New Conversation</h1>
            <p className="modal-subtitle">{conversationName}</p>
          </div>
          {onClose ? (
            <button aria-label="Close" className="modal-close" onClick={onClose} type="button">
              <X size={18} />
            </button>
          ) : (
            <UserRound size={22} />
          )}
        </div>

        <div className="modal-grid">
          <Field label="Patient name" name="fullName" onChange={update} placeholder="Nguyen Van A" value={form.fullName} />
          <Field label="Age" name="age" onChange={update} type="number" value={form.age} />
          <label className="field">
            <span>Sex</span>
            <select name="sex" onChange={update} value={form.sex}>
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
          <TextField
            label="Current medications"
            name="medications"
            onChange={update}
            placeholder="metoprolol, furosemide..."
            value={form.medications}
          />
          <TextField
            label="Allergies"
            name="allergies"
            onChange={update}
            placeholder="penicillin, aspirin, no known drug allergies"
            value={form.allergies}
          />
          <TextField
            label="Red flags"
            name="redFlags"
            onChange={update}
            placeholder="acute decompensation, chest pain, stable"
            value={form.redFlags}
          />
        </div>

        <button className="primary-action" disabled={!form.fullName.trim()} type="submit">
          Start conversation
        </button>
      </form>
    </div>
  );
}
