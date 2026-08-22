"use client";

import { useState } from "react";
import { runEval, EvalResult } from "@/lib/ws";

export default function EvalPage() {
  const [result, setResult] = useState<EvalResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRun() {
    setLoading(true);
    setError(null);
    try {
      const res = await runEval();
      setResult(res);
    } catch {
      setError("Couldn't reach the backend — is it running?");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-8">
      <div className="flex items-end justify-between gap-4">
        <div>
          <h1 className="text-4xl font-bold tracking-tight" style={{ color: "var(--text)" }}>
            Eval Scoreboard
          </h1>
          <p className="mt-2 text-lg" style={{ color: "var(--text-secondary)" }}>
            Run 22 automated chaos scenarios and see if the system survives all of them.
          </p>
        </div>
        <button
          onClick={handleRun}
          disabled={loading}
          className="shrink-0 rounded-xl px-6 py-3 text-base font-semibold transition-all hover:scale-[1.02] active:scale-[0.98] disabled:opacity-40"
          style={{ background: "var(--accent)", color: "white" }}
        >
          {loading ? "⏳ Running…" : "▶ Run All Tests"}
        </button>
      </div>

      {error && (
        <div className="animate-fade-in rounded-xl px-5 py-4 text-base"
          style={{ background: "var(--red-bg)", border: "1px solid var(--red-border)", color: "var(--red)" }}>
          ⚠️ {error}
        </div>
      )}

      {loading && (
        <div className="flex flex-col items-center justify-center rounded-2xl py-20"
          style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)" }}>
          <span className="text-5xl">🧪</span>
          <p className="mt-4 text-xl font-medium" style={{ color: "var(--text-secondary)" }}>
            Running 22 chaos scenarios…
          </p>
          <p className="mt-1 text-base" style={{ color: "var(--text-muted)" }}>
            This takes about 50 seconds — injecting faults, running tasks, and scoring results.
          </p>
          <div className="mt-6 h-1.5 w-56 overflow-hidden rounded-full" style={{ background: "var(--surface-2)" }}>
            <div className="h-full animate-pulse rounded-full" style={{ background: "var(--accent)", width: "65%" }} />
          </div>
        </div>
      )}

      {result && !loading && (
        <>
          {/* Score cards */}
          <div className="grid grid-cols-3 gap-4">
            <ScoreCard
              value={`${result.passed}/${result.total}`}
              label="Scenarios Passed"
              color={result.passed === result.total ? "var(--green)" : "var(--amber)"}
              icon={result.passed === result.total ? "✅" : "⚠️"}
            />
            <ScoreCard
              value={`${result.avg_recovery_ms}ms`}
              label="Avg Recovery Time"
              color="var(--blue)"
              icon="⚡"
            />
            <ScoreCard
              value={`${Math.round((result.passed / result.total) * 100)}%`}
              label="Pass Rate"
              color="var(--green)"
              icon="📊"
            />
          </div>

          {/* Results table */}
          <div className="overflow-x-auto rounded-2xl" style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)" }}>
            <table className="w-full text-base">
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                  <th className="px-5 py-4 text-left text-sm font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Test</th>
                  <th className="px-5 py-4 text-left text-sm font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Result</th>
                  <th className="px-5 py-4 text-left text-sm font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>Time</th>
                  <th className="px-5 py-4 text-left text-sm font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>What happened</th>
                </tr>
              </thead>
              <tbody>
                {result.results.map((r) => (
                  <tr key={r.id} style={{ borderBottom: "1px solid var(--border-subtle)" }}>
                    <td className="px-5 py-3 font-mono text-sm" style={{ color: "var(--text-muted)" }}>{r.id}</td>
                    <td className="px-5 py-3">
                      <span className="rounded-full px-3 py-1 text-sm font-semibold"
                        style={{
                          background: r.passed ? "var(--green-bg)" : "var(--red-bg)",
                          color: r.passed ? "var(--green)" : "var(--red)",
                          border: `1px solid ${r.passed ? "var(--green-border)" : "var(--red-border)"}`,
                        }}>
                        {r.passed ? "✅ Pass" : "❌ Fail"}
                      </span>
                    </td>
                    <td className="px-5 py-3 font-mono text-sm" style={{ color: "var(--text-muted)" }}>{r.recovery_ms}ms</td>
                    <td className="px-5 py-3 text-sm" style={{ color: "var(--text-secondary)" }}>{r.notes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {!result && !loading && !error && (
        <div className="flex flex-col items-center justify-center rounded-2xl border-2 border-dashed py-20"
          style={{ borderColor: "var(--border-subtle)" }}>
          <span className="text-5xl">🧪</span>
          <p className="mt-4 text-xl font-medium" style={{ color: "var(--text-secondary)" }}>
            Click <strong>Run All Tests</strong> to see if the system passes every scenario
          </p>
        </div>
      )}
    </div>
  );
}

function ScoreCard({ value, label, color, icon }: { value: string; label: string; color: string; icon: string }) {
  return (
    <div className="animate-fade-in rounded-2xl px-6 py-5"
      style={{ background: "var(--surface)", border: "1px solid var(--border-subtle)" }}>
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <div className="text-3xl font-bold" style={{ color }}>{value}</div>
          <div className="mt-0.5 text-sm" style={{ color: "var(--text-muted)" }}>{label}</div>
        </div>
      </div>
    </div>
  );
}
