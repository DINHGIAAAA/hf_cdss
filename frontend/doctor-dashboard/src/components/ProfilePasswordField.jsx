import { useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";

import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

export function ProfilePasswordField({
  autoComplete,
  className,
  hint,
  id: idProp,
  label,
  onChange,
  value,
  ...rest
}) {
  const generatedId = useId();
  const inputId = idProp || generatedId;
  const [visible, setVisible] = useState(false);

  return (
    <div className={cn("profile-password-field", className)}>
      <label className="profile-password-field__label" htmlFor={inputId}>
        {label}
      </label>
      <div className="profile-password-field__control">
        <Input
          autoComplete={autoComplete}
          className="profile-password-field__input"
          id={inputId}
          onChange={onChange}
          type={visible ? "text" : "password"}
          value={value}
          {...rest}
        />
        <button
          aria-controls={inputId}
          aria-label={visible ? "Hide password" : "Show password"}
          className="profile-password-field__toggle"
          onClick={() => setVisible((v) => !v)}
          type="button"
        >
          {visible ? <EyeOff aria-hidden size={18} /> : <Eye aria-hidden size={18} />}
        </button>
      </div>
      {hint ? <p className="profile-password-field__hint">{hint}</p> : null}
    </div>
  );
}
