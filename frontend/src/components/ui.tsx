"use client";

import React from "react";

// ---------------------------------------------------------------------------
// StatusBadge — human-readable state with icon + label + optional detail
// ---------------------------------------------------------------------------

const STATE_CONFIG: Record<
  string,
  { icon: string; label: string; human: string; color: string; bg: string; border: string }
> = {
  HEALTHY: {
    icon: "✅",
    label: "Healthy",
    human: "Working normally",
    color: "var(--green)",
    bg: "var(--green-bg)",
    border: "var(--green-border)",
  },
  DEGRADED: {
    icon: "⚠️",
    label: "Struggling",
    human: "Having issues, trying to recover",
    color: "var(--amber)",
    bg: "var(--amber-bg)",
    border: "var(--amber-border)",
  },
  CIRCUIT_OPEN: {
    icon: "❌",
    label: "Paused",
    human: "Temporarily stopped — too many failures",
    color: "var(--red)",
    bg: "var(--red-bg)",
    border: "var(--red-border)",
  },
  RECOVERING: {
    icon: "🔄",
    label: "Recovering",
    human: "Testing if it's safe to use again",
    color: "var(--blue)",
    bg: "var(--blue-bg)",
    border: "var(--blue-border)",
  },
  ESCALATED: {
    icon: "🙋",
    label: "Needs Human",
    human: "Flagged for human review",
    color: "var(--text-muted)",
    bg: "rgba(113, 113, 122, 0.08)",
    border: "rgba(113, 113, 122, 0.25)",
  },
};

export function StatusBadge({
  state,
  toolName,
  size = "normal",
}: {
  state: string;
  toolName?: string;
  size?: "compact" | "normal";
}) {
  const c = STATE_CONFIG[state] || STATE_CONFIG.HEALTHY;

  if (size === "compact") {
    return (
      <span
        className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-sm font-medium"
        style={{ background: c.bg, color: c.color, border: `1px solid ${c.border}` }}
      >
        <span>{c.icon}</span>
        <span>{c.label}</span>
      </span>
    );
  }

  return (
    <div
      className="rounded-xl px-4 py-3"
      style={{ background: c.bg, border: `1px solid ${c.border}` }}
    >
      <div className="flex items-center gap-2">
        <span className="text-lg">{c.icon}</span>
        <span className="text-base font-semibold" style={{ color: c.color }}>
          {toolName || c.label}
        </span>
      </div>
      <p className="mt-0.5 text-sm" style={{ color: "var(--text-secondary)" }}>
        {c.human}
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TOOL_LABELS — friendly names for tools
// ---------------------------------------------------------------------------

export const TOOL_LABELS: Record<string, string> = {
  lookup_booking: "Booking Lookup",
  check_availability: "Availability Check",
  charge_fare_difference: "Payment",
  send_confirmation: "Confirmation",
};

export const TOOL_DESCRIPTIONS: Record<string, string> = {
  lookup_booking: "Find the passenger's booking details",
  check_availability: "Check if seats are available on the new date",
  charge_fare_difference: "Process the fare difference payment",
  send_confirmation: "Send the updated itinerary to the passenger",
};

// ---------------------------------------------------------------------------
// StoryStep — large narrative card for timeline events
// ---------------------------------------------------------------------------

export function StoryStep({
  icon,
  headline,
  detail,
  color,
  borderColor,
  bgColor,
  timestamp,
  children,
  className = "",
}: {
  icon: string;
  headline: React.ReactNode;
  detail?: React.ReactNode;
  color: string;
  borderColor: string;
  bgColor: string;
  timestamp?: string;
  children?: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`animate-fade-in rounded-2xl px-6 py-5 ${className}`}
      style={{
        background: bgColor,
        border: `1px solid ${borderColor}`,
      }}
    >
      <div className="flex items-start gap-4">
        <span className="mt-0.5 text-2xl shrink-0">{icon}</span>
        <div className="flex-1 min-w-0">
          <div className="text-lg font-semibold leading-snug" style={{ color }}>
            {headline}
          </div>
          {detail && (
            <div className="mt-1 text-base" style={{ color: "var(--text-secondary)" }}>
              {detail}
            </div>
          )}
          {children}
        </div>
        {timestamp && (
          <span
            className="shrink-0 rounded-full px-3 py-1 text-xs font-mono"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// FailoverBanner — full-width animated banner for model failover
// ---------------------------------------------------------------------------

export function FailoverBanner({
  fromModel,
  toModel,
  reason,
  timestamp,
}: {
  fromModel: string;
  toModel: string;
  reason: string;
  timestamp?: string;
}) {
  const friendlyFrom = friendlyModelName(fromModel);
  const friendlyTo = friendlyModelName(toModel);

  return (
    <div
      className="animate-failover rounded-2xl px-6 py-6 border-2"
      style={{
        background: "linear-gradient(135deg, rgba(249, 115, 22, 0.06) 0%, rgba(249, 115, 22, 0.12) 100%)",
        borderColor: "var(--orange)",
      }}
    >
      <div className="flex items-center gap-4">
        <span className="text-4xl">🔄</span>
        <div className="flex-1">
          <div
            className="text-2xl font-bold tracking-tight"
            style={{ color: "var(--orange)" }}
          >
            Switched to backup AI model
          </div>
          <p className="mt-1 text-lg" style={{ color: "var(--text)" }}>
            The {friendlyFrom} wasn&apos;t available, so the system seamlessly switched to{" "}
            <strong>{friendlyTo}</strong> to keep going.
          </p>
          <p className="mt-1 text-sm" style={{ color: "var(--text-muted)" }}>
            Reason: {reason}
          </p>
        </div>
        {timestamp && (
          <span
            className="shrink-0 rounded-full px-3 py-1 text-xs font-mono"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}

function friendlyModelName(name: string): string {
  if (name === "primary") return "primary AI model";
  if (name === "secondary") return "backup model";
  return name;
}

// ---------------------------------------------------------------------------
// ReasoningCard — hero-style quote card for strategy reasoning
// ---------------------------------------------------------------------------

export function ReasoningCard({
  strategy,
  reasoning,
  model,
  backoff,
  tool,
  timestamp,
}: {
  strategy: string;
  reasoning: string;
  model: string;
  backoff?: number | null;
  tool: string;
  timestamp?: string;
}) {
  const friendlyStrategy = STRATEGY_LABELS[strategy] || strategy;
  const stratColor = STRATEGY_COLORS[strategy] || "var(--accent)";

  return (
    <div
      className="animate-fade-in rounded-2xl px-6 py-6"
      style={{
        background: "linear-gradient(135deg, rgba(99, 102, 241, 0.05) 0%, rgba(99, 102, 241, 0.1) 100%)",
        border: "1px solid rgba(99, 102, 241, 0.3)",
      }}
    >
      <div className="flex items-start gap-4">
        <span className="mt-0.5 text-3xl shrink-0">🧠</span>
        <div className="flex-1">
          <div className="flex items-center gap-3 flex-wrap">
            <span
              className="rounded-full px-4 py-1 text-sm font-bold uppercase tracking-wide"
              style={{ background: `${stratColor}22`, color: stratColor }}
            >
              {friendlyStrategy}
            </span>
            <span className="text-sm" style={{ color: "var(--text-muted)" }}>
              decided by <strong style={{ color: "var(--purple)" }}>{model}</strong> model
              {backoff != null && <> · waiting {backoff}s</>}
            </span>
          </div>
          <blockquote
            className="mt-3 text-xl font-medium leading-relaxed"
            style={{
              color: "var(--text)",
              borderLeft: "3px solid var(--accent)",
              paddingLeft: "16px",
            }}
          >
            &ldquo;{reasoning}&rdquo;
          </blockquote>
          <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
            The system analyzed the failure on{" "}
            <strong>{TOOL_LABELS[tool] || tool}</strong> and chose this strategy
            automatically.
          </p>
        </div>
        {timestamp && (
          <span
            className="shrink-0 rounded-full px-3 py-1 text-xs font-mono"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}

const STRATEGY_LABELS: Record<string, string> = {
  RETRY_IMMEDIATE: "Retry Now",
  RETRY_WITH_BACKOFF: "Wait & Retry",
  SWITCH_MODEL: "Switch Model",
  SERVE_CACHED: "Use Cached Data",
  ESCALATE_TO_HUMAN: "Escalate to Human",
};

const STRATEGY_COLORS: Record<string, string> = {
  RETRY_IMMEDIATE: "var(--green)",
  RETRY_WITH_BACKOFF: "var(--amber)",
  SWITCH_MODEL: "var(--orange)",
  SERVE_CACHED: "var(--blue)",
  ESCALATE_TO_HUMAN: "var(--red)",
};

// ---------------------------------------------------------------------------
// EscalationBanner — calm, resolution-styled escalation display
// ---------------------------------------------------------------------------

export function EscalationBanner({
  tool,
  reason,
  timestamp,
}: {
  tool: string;
  reason: string;
  timestamp?: string;
}) {
  return (
    <div
      className="animate-fade-in rounded-2xl px-6 py-6 border-2"
      style={{
        background: "linear-gradient(135deg, rgba(113, 113, 122, 0.05) 0%, rgba(113, 113, 122, 0.1) 100%)",
        borderColor: "var(--text-muted)",
      }}
    >
      <div className="flex items-start gap-4">
        <span className="text-3xl shrink-0">🙋</span>
        <div className="flex-1">
          <div className="text-xl font-bold" style={{ color: "var(--text)" }}>
            This step needs a human
          </div>
          <p className="mt-1 text-lg" style={{ color: "var(--text-secondary)" }}>
            The system flagged <strong>{TOOL_LABELS[tool] || tool}</strong> for
            human review rather than guessing.
          </p>
          <p className="mt-2 text-sm" style={{ color: "var(--text-muted)" }}>
            Why: {reason}
          </p>
        </div>
        {timestamp && (
          <span
            className="shrink-0 rounded-full px-3 py-1 text-xs font-mono"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// CompletionBanner — task finished summary
// ---------------------------------------------------------------------------

export function CompletionBanner({
  success,
  degraded,
  completedTools,
  escalatedTools,
  timestamp,
}: {
  success: boolean;
  degraded: boolean;
  completedTools?: string[];
  escalatedTools?: string[];
  timestamp?: string;
}) {
  const icon = success ? "✅" : "❌";
  const title = success
    ? degraded
      ? "Task finished — with some steps needing human help"
      : "Task completed successfully!"
    : "Task could not be completed";
  const color = success ? "var(--green)" : "var(--red)";
  const bg = success ? "var(--green-bg)" : "var(--red-bg)";
  const border = success ? "var(--green-border)" : "var(--red-border)";

  return (
    <div
      className="animate-fade-in rounded-2xl px-6 py-6 border-2"
      style={{ background: bg, borderColor: border }}
    >
      <div className="flex items-start gap-4">
        <span className="text-4xl shrink-0">{icon}</span>
        <div className="flex-1">
          <div className="text-2xl font-bold" style={{ color }}>
            {title}
          </div>
          {completedTools && completedTools.length > 0 && (
            <p className="mt-2 text-base" style={{ color: "var(--text-secondary)" }}>
              ✅ Completed:{" "}
              {completedTools.map((t) => TOOL_LABELS[t] || t).join(", ")}
            </p>
          )}
          {escalatedTools && escalatedTools.length > 0 && (
            <p className="mt-1 text-base" style={{ color: "var(--text-muted)" }}>
              🙋 Needs human review:{" "}
              {escalatedTools.map((t) => TOOL_LABELS[t] || t).join(", ")}
            </p>
          )}
          {degraded && (
            <span
              className="mt-3 inline-block rounded-full px-3 py-1 text-sm font-medium"
              style={{ background: "var(--amber-bg)", color: "var(--amber)", border: `1px solid var(--amber-border)` }}
            >
              ⚠️ Degraded — not all steps could run automatically
            </span>
          )}
        </div>
        {timestamp && (
          <span
            className="shrink-0 rounded-full px-3 py-1 text-xs font-mono"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {timestamp}
          </span>
        )}
      </div>
    </div>
  );
}
