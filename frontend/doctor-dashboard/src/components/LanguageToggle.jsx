import { Languages } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export function LanguageToggle({
  language,
  languages,
  onChange,
  compact = false,
  variant = "sidebar",
  className,
}) {
  const isSidebar = variant === "sidebar";
  return (
    <div
      aria-label="Chat language"
      className={cn(
        "inline-flex max-w-full items-center gap-1 rounded-full border p-1",
        isSidebar
          ? "border-sidebar-border bg-sidebar-accent/60"
          : "border-border bg-muted/60",
        compact ? "flex-col gap-0.5 p-0.5" : "min-w-0 flex-wrap justify-center",
        className,
      )}
      role="group"
    >
      {!compact && (
        <Languages
          aria-hidden="true"
          className={cn("mx-1", isSidebar ? "text-sidebar-foreground/70" : "text-muted-foreground")}
          size={15}
        />
      )}
      {languages.map((item) => (
        <Button
          aria-label={item.title}
          aria-pressed={language === item.code}
          className={cn(
            "h-7 min-w-8 rounded-full px-2 text-xs",
            isSidebar
              ? "text-sidebar-foreground/80 hover:bg-sidebar-accent hover:text-sidebar-foreground"
              : "text-muted-foreground hover:bg-background hover:text-foreground",
            language === item.code && "bg-primary text-primary-foreground hover:bg-primary/90 hover:text-primary-foreground",
          )}
          key={item.code}
          onClick={() => onChange(item.code)}
          size="sm"
          title={item.title}
          type="button"
          variant="ghost"
        >
          {item.label}
        </Button>
      ))}
    </div>
  );
}
