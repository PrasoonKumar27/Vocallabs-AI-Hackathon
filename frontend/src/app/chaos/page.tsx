"use client";

import { useState } from "react";
import { setChaos } from "@/lib/ws";

// ---------------------------------------------------------------------------
// Tool definitions with friendly names
// ---------------------------------------------------------------------------
const TOOLS = [
  {
    id: "lookup_booking",
    label: "Booking Lookup",
    desc: "Finds the passenger's booking",
    icon: "🔍",
  },
  {
    id: "check_availability",
    label: "Availability Check",
    desc: "Checks seat availability",
    icon: "📅",
  },
  {
    id: "charge_fare_difference",
    label: "Payment",
    desc: "Charges the fare difference",
    icon: "💳",
  },
  {
    id: "send_confirmation",
    label: "Confirmation",
    desc: "Sends updated itinerary",
    icon: "✉️",
  },
];

// ---------------------------------------------------------------------------
// Fault definitions with friendly names and human descriptions
// ---------------------------------------------------------------------------
const FAULTS = [
  {
    id: "ERROR_500",
    label: "Make it crash",
    desc: "The tool will throw a server error (500)",
    color: "var(--red)",
    bg: "var(--red-bg)",
    border: "var(--red-border)",
    icon: "💥",
  },
  {
    id: "CORRUPT_PAYLOAD",
    label: "Send bad data",
    desc: "The tool will return garbled, wrong-typed data",
    color: "var(--orange)",
    bg: "var(--orange-bg)",
    border: "var(--orange-border)",
    icon: "🗑️",
  },
  {
    id: "LATENCY_SPIKE",
    label: "Make it slow",
    desc: "The tool will take 4+ seconds to respond",
    color: "var(--amber)",
    bg: "var(--amber-bg)",
    border: "var(--amber-border)",
    icon: "🐢",
  },
  {
    id: "SILENT_NULL",
    label: "Return nothing",
    desc: "The tool will respond with empty data, no error",
    color: "var(--purple)",
    bg: "var(--purple-bg)",
    border: "var(--purple-border)",
    icon: "👻",
  },
  {
    id: "RATE_LIMIT",
    label: "Block it",
    desc: "The tool will reject the call (rate limit 429)",
    color: "var(--blue)",
    bg: "var(--blue-bg)",
    border: "var(--blue-border)",
    icon: "🚫",
  },
];

// ---------------------------------------------------------------------------
// Friendly toast messages
// ---------------------------------------------------------------------------
function toastMessage(tool: typeof TOOLS[0], fault: typeof FAULTS[0], count: number): string {
  const times = count === 1 ? "the next call" : `the next ${count} calls`;
  return `Got it — ${times} to ${tool.label} will ${fault.desc.toLowerCase().replace("the tool will ", "")}.`;
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------
export default function ChaosConsolePage() {
  const [selectedTool, setSelectedTool] = useState<string | null>(null);
  const [count, setCount] = useState(1);
  const [toast, setToast] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  async function inject(toolId: string, faultId: string) {
    setSending(true);
    try {
      await setChaos(toolId, faultId, count);
      const tool = TOOLS.find((t) => t.id === toolId)!;
      const fault = FAULTS.find((f) => f.id === faultId)!;
      setToast(toastMessage(tool, fault, count));
      setTimeout(() => setToast(null), 5000);
    } catch {
      setToast("⚠️ Couldn't reach the backend — is it running?");
      setTimeout(() => setToast(null), 5000);
    } finally {
      setSending(false);
    }
  }

  async function clearTool(toolId: string) {
    await setChaos(toolId, "NONE", 0);
    const tool = TOOLS.find((t) => t.id === toolId)!;
    setToast(`✅ Cleared all faults on ${tool.label}`);
    setTimeout(() => setToast(null), 3000);
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div>
        <h1
          className="text-4xl font-bold tracking-tight"
          style={{ color: "var(--text)" }}
        >
          Chaos Console
        </h1>
        <p className="mt-2 text-lg" style={{ color: "var(--text-secondary)" }}>
          Pick a tool, pick a failure, and watch the AI agent handle it in real
          time on the{" "}
          <a href="/" className="underline" style={{ color: "var(--accent)" }}>
            Live Demo
          </a>{" "}
          page.
        </p>
      </div>

      {/* Toast */}
      {toast && (
        <div
          className="animate-fade-in rounded-xl px-5 py-4 text-base font-medium"
          style={{
            background: "var(--accent-bg)",
            border: "1px solid rgba(99, 102, 241, 0.3)",
            color: "var(--accent)",
          }}
        >
          {toast}
        </div>
      )}

      {/* Step 1: Pick a tool */}
      <div>
        <h2
          className="text-sm font-semibold uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          Step 1 — Pick the tool to break
        </h2>
        <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {TOOLS.map((tool) => {
            const isSelected = selectedTool === tool.id;
            return (
              <button
                key={tool.id}
                onClick={() => setSelectedTool(tool.id)}
                className="rounded-2xl px-5 py-4 text-left transition-all hover:scale-[1.02] active:scale-[0.98]"
                style={{
                  background: isSelected ? "var(--accent-bg)" : "var(--surface)",
                  border: isSelected
                    ? "2px solid var(--accent)"
                    : "2px solid var(--border-subtle)",
                }}
              >
                <span className="text-3xl">{tool.icon}</span>
                <div className="mt-2 text-base font-semibold">{tool.label}</div>
                <div
                  className="mt-0.5 text-sm"
                  style={{ color: "var(--text-muted)" }}
                >
                  {tool.desc}
                </div>
              </button>
            );
          })}
        </div>
      </div>

      {/* Step 2: Pick how many times */}
      {selectedTool && (
        <div className="animate-fade-in">
          <h2
            className="text-sm font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Step 2 — How many times should it fail?
          </h2>
          <div className="mt-3 flex items-center gap-2">
            {[1, 2, 3, 5].map((n) => (
              <button
                key={n}
                onClick={() => setCount(n)}
                className="rounded-xl px-5 py-2.5 text-base font-semibold transition-all"
                style={{
                  background: count === n ? "var(--accent)" : "var(--surface)",
                  color: count === n ? "white" : "var(--text-secondary)",
                  border:
                    count === n
                      ? "2px solid var(--accent)"
                      : "2px solid var(--border-subtle)",
                }}
              >
                {n}×
              </button>
            ))}
            <span className="ml-2 text-sm" style={{ color: "var(--text-muted)" }}>
              consecutive calls
            </span>
          </div>
          {count >= 2 && (
            <p className="mt-2 text-sm" style={{ color: "var(--amber)" }}>
              💡 Tip: 2+ failures on the Payment tool triggers the safety-net
              escalation — try it!
            </p>
          )}
        </div>
      )}

      {/* Step 3: Pick the failure type */}
      {selectedTool && (
        <div className="animate-fade-in">
          <h2
            className="text-sm font-semibold uppercase tracking-widest"
            style={{ color: "var(--text-muted)" }}
          >
            Step 3 — Pick the failure to inject
          </h2>
          <div className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {FAULTS.map((fault) => (
              <button
                key={fault.id}
                onClick={() => inject(selectedTool, fault.id)}
                disabled={sending}
                className="group rounded-2xl px-5 py-4 text-left transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-50"
                style={{
                  background: fault.bg,
                  border: `2px solid ${fault.border}`,
                }}
              >
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{fault.icon}</span>
                  <div>
                    <div
                      className="text-base font-semibold"
                      style={{ color: fault.color }}
                    >
                      {fault.label}
                    </div>
                    <div
                      className="text-sm"
                      style={{ color: "var(--text-muted)" }}
                    >
                      {fault.desc}
                    </div>
                  </div>
                </div>
              </button>
            ))}
          </div>

          {/* Clear button */}
          <button
            onClick={() => clearTool(selectedTool)}
            className="mt-3 rounded-xl px-5 py-2.5 text-sm font-medium transition-all hover:opacity-80"
            style={{
              background: "var(--surface)",
              border: "1px solid var(--border-subtle)",
              color: "var(--text-muted)",
            }}
          >
            🧹 Clear all faults on{" "}
            {TOOLS.find((t) => t.id === selectedTool)?.label}
          </button>
        </div>
      )}

      {/* Idle prompt */}
      {!selectedTool && (
        <div
          className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed py-16"
          style={{ borderColor: "var(--border-subtle)" }}
        >
          <span className="text-4xl">👆</span>
          <p
            className="mt-3 text-lg font-medium"
            style={{ color: "var(--text-secondary)" }}
          >
            Select a tool above to get started
          </p>
        </div>
      )}
    </div>
  );
}
