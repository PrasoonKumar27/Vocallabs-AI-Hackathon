"use client";

import { useState, useEffect, useRef, useMemo } from "react";
import { useTaskEvents, startTask, TaskEvent } from "@/lib/ws";
import {
  StatusBadge,
  StoryStep,
  FailoverBanner,
  ReasoningCard,
  EscalationBanner,
  CompletionBanner,
  TOOL_LABELS,
  TOOL_DESCRIPTIONS,
} from "@/components/ui";

// ---------------------------------------------------------------------------
// Friendly fault names
// ---------------------------------------------------------------------------
const FAULT_LABELS: Record<string, string> = {
  ERROR_500: "a server crash",
  RATE_LIMIT: "a rate limit",
  LATENCY_SPIKE: "a slow response",
  SILENT_NULL: "an empty response",
  CORRUPT_PAYLOAD: "corrupted data",
};

// ---------------------------------------------------------------------------
// Main Page
// ---------------------------------------------------------------------------
export default function TaskViewPage() {
  const [taskId, setTaskId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const { events, connected } = useTaskEvents(taskId);
  const bottomRef = useRef<HTMLDivElement>(null);

  const toolStates = useMemo(() => deriveToolStates(events), [events]);
  const isComplete = events.some((e) => e.event === "task_completed");

  // Deduplicate consecutive model_failover events for cleaner display
  const displayEvents = useMemo(() => dedupeFailovers(events), [events]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  async function handleStart() {
    setStarting(true);
    try {
      const id = await startTask("Reschedule booking BKG123 to 2026-09-15");
      setTaskId(id);
    } catch (err) {
      console.error("Failed to start task:", err);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-8">
      {/* Hero header */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1
            className="text-4xl font-bold tracking-tight"
            style={{ color: "var(--text)" }}
          >
            Live Demo
          </h1>
          <p
            className="mt-2 text-lg"
            style={{ color: "var(--text-secondary)" }}
          >
            Watch an AI agent reschedule a flight booking — and survive whatever
            you throw at it.
          </p>
        </div>
        <div className="flex items-center gap-3 shrink-0">
          {taskId && connected && (
            <span className="flex items-center gap-1.5 text-sm" style={{ color: "var(--green)" }}>
              <span className="animate-pulse-dot inline-block h-2 w-2 rounded-full bg-green-500" />
              Live
            </span>
          )}
          <button
            onClick={handleStart}
            disabled={starting || (!!taskId && !isComplete)}
            className="rounded-xl px-6 py-3 text-base font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40 disabled:hover:scale-100"
            style={{ background: "var(--accent)", color: "white" }}
          >
            {starting
              ? "Starting…"
              : taskId && !isComplete
              ? "⏳ Running…"
              : "▶ Start Task"}
          </button>
        </div>
      </div>

      {/* Tool status bar */}
      {taskId && Object.keys(toolStates).length > 0 && (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Object.entries(TOOL_LABELS).map(([key, label]) => {
            const state = toolStates[key] || "HEALTHY";
            return (
              <StatusBadge key={key} state={state} toolName={label} />
            );
          })}
        </div>
      )}

      {/* Event timeline — narrative cards */}
      {taskId && (
        <div className="space-y-4">
          {displayEvents.map((ev, i) => (
            <EventCard key={i} event={ev} />
          ))}
          <div ref={bottomRef} />
        </div>
      )}

      {/* Empty state */}
      {!taskId && (
        <div
          className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed py-20"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <span className="text-5xl">⚡</span>
          <p
            className="mt-4 text-xl font-medium"
            style={{ color: "var(--text-secondary)" }}
          >
            Waiting for the agent to start…
          </p>
          <p className="mt-2 text-base" style={{ color: "var(--text-muted)" }}>
            Click <strong>Start Task</strong> above, then open the{" "}
            <strong>Chaos Console</strong> to inject failures mid-run.
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// EventCard — renders a single event as a narrative card
// ---------------------------------------------------------------------------
function EventCard({ event }: { event: TaskEvent }) {
  const ts = new Date(event.ts).toLocaleTimeString();

  switch (event.event) {
    case "tool_call_started": {
      const toolName = TOOL_LABELS[event.tool] || event.tool;
      const toolDesc = TOOL_DESCRIPTIONS[event.tool] || "";
      const isRetry = event.attempt > 1;
      return (
        <StoryStep
          icon={isRetry ? "🔁" : "🔧"}
          headline={
            isRetry
              ? `Retrying ${toolName} (attempt ${event.attempt})`
              : `Agent is calling ${toolName}`
          }
          detail={isRetry ? `Previous attempt failed — trying again.` : toolDesc}
          color="var(--text)"
          borderColor="var(--border-subtle)"
          bgColor="var(--surface)"
          timestamp={ts}
        />
      );
    }

    case "fault_detected": {
      const toolName = TOOL_LABELS[event.tool] || event.tool;
      const faultName = FAULT_LABELS[event.fault_type] || event.fault_type;
      return (
        <StoryStep
          icon="⚠️"
          headline={`Something went wrong with ${toolName}`}
          detail={`The tool hit ${faultName}. The system is analyzing what to do next.`}
          color="var(--amber)"
          borderColor="var(--amber-border)"
          bgColor="var(--amber-bg)"
          timestamp={ts}
        >
          <span
            className="mt-2 inline-block rounded-full px-3 py-1 text-xs font-mono uppercase"
            style={{ background: "var(--surface-2)", color: "var(--text-muted)" }}
          >
            {event.fault_type}
          </span>
        </StoryStep>
      );
    }

    case "strategy_chosen":
      return (
        <ReasoningCard
          strategy={event.strategy}
          reasoning={event.reasoning}
          model={event.model}
          backoff={event.seconds}
          tool={event.tool}
          timestamp={ts}
        />
      );

    case "state_transition": {
      const toolName = TOOL_LABELS[event.tool] || event.tool;
      const stateMessages: Record<string, string> = {
        DEGRADED: `${toolName} is struggling — the system noticed a failure and is on alert.`,
        CIRCUIT_OPEN: `${toolName} is temporarily paused — the system noticed repeated failures and is protecting itself.`,
        RECOVERING: `${toolName} is being tested — the system is checking if it's safe to use again.`,
        ESCALATED: `${toolName} has been flagged for human review — the system decided not to guess.`,
        HEALTHY: `${toolName} is back to normal.`,
      };
      const msg = stateMessages[event.to] || `${toolName} changed from ${event.from} to ${event.to}`;
      return (
        <StoryStep
          icon={event.to === "HEALTHY" ? "✅" : event.to === "ESCALATED" ? "🙋" : "📊"}
          headline={msg}
          color={
            event.to === "HEALTHY"
              ? "var(--green)"
              : event.to === "ESCALATED"
              ? "var(--text-muted)"
              : "var(--amber)"
          }
          borderColor="var(--border-subtle)"
          bgColor="var(--surface)"
          timestamp={ts}
        >
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge state={event.from} size="compact" />
            <span style={{ color: "var(--text-muted)" }}>→</span>
            <StatusBadge state={event.to} size="compact" />
          </div>
        </StoryStep>
      );
    }

    case "model_failover":
      return (
        <FailoverBanner
          fromModel={event.from_model}
          toModel={event.to_model}
          reason={event.reason}
          timestamp={ts}
        />
      );

    case "escalated":
      return (
        <EscalationBanner tool={event.tool} reason={event.reason} timestamp={ts} />
      );

    case "task_completed":
      return (
        <CompletionBanner
          success={event.success}
          degraded={event.degraded}
          completedTools={event.completed_tools}
          escalatedTools={event.escalated_tools}
          timestamp={ts}
        />
      );

    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function deriveToolStates(events: TaskEvent[]): Record<string, string> {
  const states: Record<string, string> = {};
  for (const ev of events) {
    if (ev.event === "state_transition") {
      states[ev.tool] = ev.to;
    }
  }
  return states;
}

/**
 * Collapses consecutive model_failover events into a single one
 * so the UI doesn't flood with repeated failover banners.
 */
function dedupeFailovers(events: TaskEvent[]): TaskEvent[] {
  const result: TaskEvent[] = [];
  for (const ev of events) {
    if (ev.event === "model_failover") {
      const prev = result[result.length - 1];
      if (prev && prev.event === "model_failover") {
        continue; // skip consecutive duplicate
      }
    }
    result.push(ev);
  }
  return result;
}
