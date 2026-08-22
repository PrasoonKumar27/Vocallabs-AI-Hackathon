"use client";

import { useEffect, useRef, useState, useCallback } from "react";

// ---------------------------------------------------------------------------
// Event types matching Section 6.6 of the shared doc
// ---------------------------------------------------------------------------

export type ToolCallStartedEvent = {
  event: "tool_call_started";
  tool: string;
  attempt: number;
  ts: string;
};

export type FaultDetectedEvent = {
  event: "fault_detected";
  tool: string;
  fault_type: string;
  ts: string;
};

export type StrategyChosenEvent = {
  event: "strategy_chosen";
  tool: string;
  strategy: string;
  seconds: number | null;
  model: string;
  reasoning: string;
  ts: string;
};

export type StateTransitionEvent = {
  event: "state_transition";
  tool: string;
  from: string;
  to: string;
  ts: string;
};

export type ModelFailoverEvent = {
  event: "model_failover";
  from_model: string;
  to_model: string;
  reason: string;
  ts: string;
};

export type EscalatedEvent = {
  event: "escalated";
  tool: string;
  reason: string;
  ts: string;
};

export type TaskCompletedEvent = {
  event: "task_completed";
  success: boolean;
  degraded: boolean;
  completed_tools?: string[];
  escalated_tools?: string[];
  error?: string;
  message?: string;
  ts: string;
};

export type TaskEvent =
  | ToolCallStartedEvent
  | FaultDetectedEvent
  | StrategyChosenEvent
  | StateTransitionEvent
  | ModelFailoverEvent
  | EscalatedEvent
  | TaskCompletedEvent;

// ---------------------------------------------------------------------------
// Hook: useTaskEvents
// ---------------------------------------------------------------------------

export function useTaskEvents(taskId: string | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const connect = useCallback(
    (id: string) => {
      if (wsRef.current) {
        wsRef.current.close();
      }

      const protocol = window.location.protocol === "https:" ? "wss" : "ws";
      const host = process.env.NEXT_PUBLIC_API_HOST || "localhost:8000";
      const url = `${protocol}://${host}/ws/task/${id}`;

      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setConnected(true);

      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as TaskEvent;
          setEvents((prev) => [...prev, event]);
        } catch {
          // ignore non-JSON messages
        }
      };

      ws.onclose = () => setConnected(false);
      ws.onerror = () => setConnected(false);
    },
    []
  );

  useEffect(() => {
    if (taskId) {
      setEvents([]);
      connect(taskId);
    }
    return () => {
      wsRef.current?.close();
    };
  }, [taskId, connect]);

  return { events, connected };
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

const API_BASE =
  typeof window !== "undefined"
    ? `${window.location.protocol}//${process.env.NEXT_PUBLIC_API_HOST || "localhost:8000"}`
    : "http://localhost:8000";

export async function startTask(request: string): Promise<string> {
  const resp = await fetch(`${API_BASE}/api/task/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request }),
  });
  const data = await resp.json();
  return data.task_id;
}

export async function setChaos(
  tool: string,
  fault: string,
  count: number
): Promise<void> {
  await fetch(`${API_BASE}/api/chaos/set`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool, fault, count }),
  });
}

export type EvalResult = {
  passed: number;
  total: number;
  avg_recovery_ms: number;
  results: {
    id: string;
    passed: boolean;
    recovery_ms: number;
    notes: string;
  }[];
};

export async function runEval(): Promise<EvalResult> {
  const resp = await fetch(`${API_BASE}/api/eval/run`);
  return resp.json();
}
