import { useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Info,
  Minus,
  Pill,
  ShieldAlert,
  TrendingUp,
} from "lucide-react";
import { useLanguage } from "@/i18n/LanguageProvider.jsx";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Status configuration with colors and icons
const STATUS_CONFIG = {
  recommended: {
    class: "bg-emerald-50 border-emerald-200 text-emerald-800",
    badge: "bg-emerald-100 text-emerald-700 border-emerald-300",
    icon: TrendingUp,
    label: { en: "Recommended", vi: "Khuyến nghị" },
  },
  maintain: {
    class: "bg-blue-50 border-blue-200 text-blue-800",
    badge: "bg-blue-100 text-blue-700 border-blue-300",
    icon: Minus,
    label: { en: "Maintain", vi: "Duy trì" },
  },
  hold: {
    class: "bg-amber-50 border-amber-200 text-amber-800",
    badge: "bg-amber-100 text-amber-700 border-amber-300",
    icon: AlertTriangle,
    label: { en: "Hold", vi: "Tạm dừng" },
  },
  needs_data: {
    class: "bg-slate-50 border-slate-200 text-slate-800",
    badge: "bg-slate-100 text-slate-700 border-slate-300",
    icon: Info,
    label: { en: "Needs Data", vi: "Cần dữ liệu" },
  },
  not_recommended: {
    class: "bg-red-50 border-red-200 text-red-800",
    badge: "bg-red-100 text-red-700 border-red-300",
    icon: ShieldAlert,
    label: { en: "Not Recommended", vi: "Không khuyến khích" },
  },
  review: {
    class: "bg-purple-50 border-purple-200 text-purple-800",
    badge: "bg-purple-100 text-purple-700 border-purple-300",
    icon: Clock,
    label: { en: "Review", vi: "Cần xem xét" },
  },
};

function formatDoseAmount(amount) {
  if (!amount || amount.value == null) return null;
  const value = amount.value % 1 === 0 ? amount.value : amount.value.toFixed(2);
  return `${value} ${amount.unit || "mg"} · ${amount.frequency || "—"}`;
}

function DoseStatusBadge({ status }) {
  const { language } = useLanguage();
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.review;
  const Icon = config.icon;
  const label = config.label[language] || config.label.en;

  return (
    <Badge className={cn("gap-1 border", config.badge)} variant="outline">
      <Icon size={12} />
      {label}
    </Badge>
  );
}

function DoseComparison({ current, recommended, target }) {
  const { language } = useLanguage();

  const items = [
    { label: language === "vi" ? "Liều hiện tại" : "Current", amount: current, color: "text-slate-600" },
    { label: language === "vi" ? "Liều đề xuất" : "Recommended", amount: recommended, color: "text-emerald-600 font-semibold" },
    { label: language === "vi" ? "Liều mục tiêu" : "Target", amount: target, color: "text-blue-600" },
  ].filter((item) => item.amount && item.amount.value != null);

  if (items.length === 0) {
    return (
      <div className="text-sm text-muted-foreground">
        {language === "vi" ? "Không có thông tin liều lượng" : "No dose information available"}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item, index) => (
        <div key={item.label} className="flex items-center gap-3">
          {index > 0 && (
            <ArrowDown size={14} className="shrink-0 text-muted-foreground" />
          )}
          <div className={cn("min-w-0 flex-1", index === 0 && "ml-5")}>
            <span className="text-xs text-muted-foreground">{item.label}</span>
            <div className={cn("text-sm", item.color)}>
              {formatDoseAmount(item.amount)}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function HoldCriteriaAlert({ criteria }) {
  const { language } = useLanguage();
  if (!criteria || criteria.length === 0) return null;

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
      <div className="flex items-start gap-2">
        <AlertTriangle size={16} className="mt-0.5 shrink-0 text-amber-600" />
        <div>
          <p className="text-xs font-semibold text-amber-800">
            {language === "vi" ? "Cảnh báo tạm dừng tăng liều" : "Hold Criteria Active"}
          </p>
          <ul className="mt-1 space-y-0.5 text-xs text-amber-700">
            {criteria.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function TitrationSteps({ plan }) {
  const { language } = useLanguage();
  if (!plan?.titration_plan || plan.titration_plan.length === 0) return null;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {language === "vi" ? "Kế hoạch tăng liều" : "Titration Plan"}
      </p>
      <div className="space-y-1.5">
        {plan.titration_plan.map((step, index) => (
          <div key={index} className="flex items-start gap-2 text-sm">
            <span className="mt-1.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-xs font-medium text-primary">
              {index + 1}
            </span>
            <span className="text-foreground/90">{step}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function CalculationSteps({ steps }) {
  const { language } = useLanguage();
  const [expanded, setExpanded] = useState(false);

  if (!steps || steps.length === 0) return null;

  return (
    <div className="space-y-2">
      <Button
        variant="ghost"
        size="sm"
        className="h-auto w-full justify-between px-2 py-1 text-xs text-muted-foreground hover:text-foreground"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="flex items-center gap-1">
          <Info size={12} />
          {language === "vi" ? "Chi tiết tính toán" : "Calculation Details"}
        </span>
        {expanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
      </Button>

      {expanded && (
        <div className="rounded-md border border-border/60 bg-muted/30 p-2">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border/60">
                <th className="pb-1 text-left font-medium text-muted-foreground">
                  {language === "vi" ? "Bước" : "Step"}
                </th>
                <th className="pb-1 text-left font-medium text-muted-foreground">
                  {language === "vi" ? "Kết quả" : "Result"}
                </th>
              </tr>
            </thead>
            <tbody className="space-y-1">
              {steps.map((step, index) => (
                <tr key={index} className="align-top">
                  <td className="pr-3 text-muted-foreground">{step.description}</td>
                  <td className="font-medium">{step.result}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function MonitoringList({ items }) {
  const { language } = useLanguage();
  if (!items || items.length === 0) return null;

  return (
    <div className="space-y-1.5">
      <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {language === "vi" ? "Theo dõi" : "Monitoring"}
      </p>
      <ul className="space-y-1">
        {items.slice(0, 3).map((item, index) => (
          <li className="flex items-start gap-1.5 text-xs text-muted-foreground" key={index}>
            <CheckCircle2 size={12} className="mt-0.5 shrink-0 text-emerald-500" />
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

function MissingInputsAlert({ inputs }) {
  const { language } = useLanguage();
  if (!inputs || inputs.length === 0) return null;

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2">
      <div className="flex items-start gap-2">
        <Info size={16} className="mt-0.5 shrink-0 text-slate-600" />
        <div>
          <p className="text-xs font-semibold text-slate-800">
            {language === "vi" ? "Thông tin còn thiếu" : "Missing Information"}
          </p>
          <p className="mt-0.5 text-xs text-slate-600">
            {language === "vi"
              ? `Cần cung cấp: ${inputs.join(", ")}`
              : `Required: ${inputs.join(", ")}`}
          </p>
        </div>
      </div>
    </div>
  );
}

function DosePlanCard({ plan }) {
  const [expanded, setExpanded] = useState(false);
  const { language } = useLanguage();
  const statusConfig = STATUS_CONFIG[plan.status] || STATUS_CONFIG.review;

  return (
    <Card className={cn("overflow-hidden transition-all", statusConfig.class)}>
      <CardHeader className="cursor-pointer py-3" onClick={() => setExpanded(!expanded)}>
        <div className="flex min-w-0 items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <Pill size={16} className="shrink-0 text-primary" />
              <CardTitle className="text-sm font-semibold">
                {plan.drug_name || plan.drug_class}
              </CardTitle>
            </div>
            {plan.drug_class && plan.drug_name && plan.drug_class !== plan.drug_name && (
              <p className="mt-0.5 text-xs text-muted-foreground">
                {plan.drug_class.replace(/_/g, " ")}
              </p>
            )}
          </div>
          <div className="flex items-center gap-2">
            <DoseStatusBadge status={plan.status} />
            {expanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </div>
        </div>
      </CardHeader>

      {expanded && (
        <CardContent className="space-y-4 border-t border-border/60 bg-background/80 px-3 py-3">
          {/* Rationale */}
          {plan.rationale && (
            <p className="text-sm text-foreground/80">{plan.rationale}</p>
          )}

          {/* Dose Comparison */}
          <div className="rounded-lg border border-border/60 bg-background p-3">
            <DoseComparison
              current={plan.current_dose}
              recommended={plan.recommended_dose}
              target={plan.target_dose}
            />
          </div>

          {/* Hold Criteria */}
          <HoldCriteriaAlert criteria={plan.hold_criteria} />

          {/* Missing Inputs */}
          <MissingInputsAlert inputs={plan.missing_inputs} />

          {/* Titration Plan */}
          <TitrationSteps plan={plan} />

          {/* Calculation Steps */}
          <CalculationSteps steps={plan.calculation_steps} />

          {/* Monitoring */}
          <MonitoringList items={plan.monitoring} />

          {/* Guideline Notes */}
          {plan.guideline_notes && plan.guideline_notes.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {language === "vi" ? "Ghi chú guideline" : "Guideline Notes"}
              </p>
              <ul className="space-y-1">
                {plan.guideline_notes.map((note, index) => (
                  <li className="flex items-start gap-1.5 text-xs text-muted-foreground" key={index}>
                    <Info size={12} className="mt-0.5 shrink-0 text-blue-500" />
                    {note}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Evidence References */}
          {plan.evidence_refs && plan.evidence_refs.length > 0 && (
            <div className="space-y-1.5">
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                {language === "vi" ? "Tài liệu tham khảo" : "Evidence"}
              </p>
              <div className="flex flex-wrap gap-1">
                {plan.evidence_refs.map((ref, index) => (
                  <Badge key={index} variant="secondary" className="text-xs">
                    {ref}
                  </Badge>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function DosePlanSummaryTable({ plans }) {
  const { language } = useLanguage();
  const [showAll, setShowAll] = useState(false);

  if (!plans || plans.length === 0) return null;

  const displayedPlans = showAll ? plans : plans.slice(0, 5);
  const hasMore = plans.length > 5;

  return (
    <div className="space-y-3">
      <div className="overflow-hidden rounded-lg border border-border">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border bg-muted/50">
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {language === "vi" ? "Thuốc" : "Drug"}
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {language === "vi" ? "Liều hiện tại" : "Current"}
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {language === "vi" ? "Liều đề xuất" : "Recommended"}
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {language === "vi" ? "Liều mục tiêu" : "Target"}
                </th>
                <th className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {language === "vi" ? "Trạng thái" : "Status"}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {displayedPlans.map((plan, index) => (
                <tr key={plan.plan_id || index} className="hover:bg-muted/30">
                  <td className="px-3 py-2">
                    <div className="font-medium">{plan.drug_name}</div>
                    <div className="text-xs text-muted-foreground">
                      {plan.drug_class?.replace(/_/g, " ")}
                    </div>
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {formatDoseAmount(plan.current_dose) || "—"}
                  </td>
                  <td className="px-3 py-2 font-medium text-emerald-700">
                    {formatDoseAmount(plan.recommended_dose) || "—"}
                  </td>
                  <td className="px-3 py-2 text-blue-700">
                    {formatDoseAmount(plan.target_dose) || "—"}
                  </td>
                  <td className="px-3 py-2">
                    <DoseStatusBadge status={plan.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {hasMore && (
        <Button
          variant="outline"
          size="sm"
          className="w-full"
          onClick={() => setShowAll(!showAll)}
        >
          {showAll
            ? language === "vi"
              ? "Thu gọn"
              : "Show Less"
            : language === "vi"
              ? `Xem thêm ${plans.length - 5} thuốc`
              : `Show ${plans.length - 5} more drugs`}
        </Button>
      )}
    </div>
  );
}

export function DosePlanDisplay({ dosePlans, version }) {
  const { language } = useLanguage();

  if (!dosePlans || dosePlans.length === 0) {
    return null;
  }

  // Group plans by status for better organization
  const activePlans = dosePlans.filter(
    (p) => p.status === "recommended" || p.status === "maintain"
  );
  const holdPlans = dosePlans.filter((p) => p.status === "hold");
  const otherPlans = dosePlans.filter(
    (p) =>
      !["recommended", "maintain", "hold"].includes(p.status)
  );

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Pill size={18} className="text-primary" />
          <h3 className="text-sm font-semibold">
            {language === "vi" ? "Kế hoạch liều lượng" : "Dose Plans"}
          </h3>
          <Badge variant="secondary" className="text-xs">
            {dosePlans.length} {language === "vi" ? "thuốc" : "drugs"}
          </Badge>
        </div>
        {version && (
          <span className="text-xs text-muted-foreground">
            v{version}
          </span>
        )}
      </div>

      {/* Summary Table */}
      <DosePlanSummaryTable plans={dosePlans} />

      {/* Detailed Cards - Active Plans */}
      {activePlans.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {language === "vi" ? "Chi tiết liều lượng" : "Detailed Dose Information"}
          </p>
          {activePlans.map((plan) => (
            <DosePlanCard key={plan.plan_id} plan={plan} />
          ))}
        </div>
      )}

      {/* Hold Plans */}
      {holdPlans.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-2">
            <AlertTriangle size={14} className="text-amber-600" />
            <p className="text-xs font-semibold uppercase tracking-wide text-amber-700">
              {language === "vi" ? "Tạm dừng tăng liều" : "Hold Titration"}
            </p>
          </div>
          {holdPlans.map((plan) => (
            <DosePlanCard key={plan.plan_id} plan={plan} />
          ))}
        </div>
      )}

      {/* Other Plans */}
      {otherPlans.length > 0 && (
        <div className="space-y-2">
          {otherPlans.map((plan) => (
            <DosePlanCard key={plan.plan_id} plan={plan} />
          ))}
        </div>
      )}
    </div>
  );
}

export { DosePlanCard, formatDoseAmount, DoseStatusBadge };
