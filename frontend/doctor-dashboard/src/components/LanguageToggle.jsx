import { Languages } from "lucide-react";

export function LanguageToggle({ language, languages, onChange, compact = false }) {
  return (
    <div
      aria-label="Chat language"
      className={`language-toggle${compact ? " language-toggle--compact" : ""}`}
      role="group"
    >
      {!compact && <Languages aria-hidden="true" size={15} />}
      {languages.map((item) => (
        <button
          aria-label={item.title}
          aria-pressed={language === item.code}
          className={language === item.code ? "active" : ""}
          key={item.code}
          onClick={() => onChange(item.code)}
          title={item.title}
          type="button"
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}
