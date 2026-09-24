import { useCallback, useEffect, useState } from "react";

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? "http://localhost:8000";

export type Verdict = "fraud" | "legitimate" | "uncertain";
export type Route = "auto" | "L1" | "L2";
export type Role = "analyst" | "L1" | "L2";

export type CaseRow = {
  case_id: string;
  opened_at: string;
  trigger_type: "risk_score" | "customer_report" | "analyst_request";
  trigger_text: string;
  card_id: string;
  customer_id: string;
  flagged_txn_id: string;
  risk_score: number | null;
  verdict: Verdict;
  fraud_probability: number;
  pattern: string;
  status: string;
  exposure_usd: number;
  sar: boolean;
  pending_approvals: number;
  evidence_requests: number;
  tool_calls: number;
  tokens: number;
  latency_s: number;
};

export type Action = { action: string; route: Route; reason: string };
export type Evidence = { claim: string; source: string; ref: string; entity_ids: string[] };
export type ActionLog = {
  ts: string;
  case_id: string;
  action: string;
  route: Route;
  actor: string;
  actor_label: string;
  status: string;
  effect: string;
};

export type Answer = {
  case_id: string;
  case: {
    status: string;
    verdict: Verdict;
    fraud_probability: number;
    pattern: string;
    pattern_description: string;
    affected_txn_ids: string[];
    first_suspicious_txn_id: string;
    connected_card_ids: string[];
    connected_device_profiles: string[];
    exposure_usd: number;
    evidence: Evidence[];
    similar_prior_cases: string[];
    summary: string;
    written_to_graph: boolean;
    graph_case_id: string;
  };
  evidence_requests: { type: string; asked_after_step: number; assumed_response: string }[];
  next_best_actions: { initial: Action[]; final: Action[]; what_changed: string };
  sar: {
    file: boolean;
    reason: string;
    narrative: string;
    subjects: string[];
    total_amount_usd: number;
    activity_dates: string[];
  };
  stop_reason: string;
  tool_calls: number;
  tokens: number;
  latency_s: number;
};

export type CaseDetail = {
  row: CaseRow;
  answer: Answer;
  timeline: { ts: string; node: string; detail: string }[];
  rationale: string;
  probability_path: { round: string; verdict: string; p: number; confidence: number | null }[];
  transactions: {
    id: string;
    ts: string | null;
    amount: number | null;
    channel: string | null;
    product_cd: string | null;
    addr1: string | null;
    risk_score: number | null;
    id_15: string | null;
    id_23: string | null;
  }[];
  similar_cases: {
    id: string;
    outcome: string | null;
    pattern: string | null;
    exposure_usd: number | null;
    analyst_notes: string | null;
    card_id: string | null;
  }[];
  actions_log: ActionLog[];
  pending: Action[];
};

export type Stats = {
  cases: number;
  verdicts: Record<string, number>;
  patterns: Record<string, number>;
  status: Record<string, number>;
  sars: number;
  exposure_usd: number;
  pending_approvals: number;
  evidence_requests: number;
  avg_latency_s: number;
};

export type GraphNode = {
  id: string;
  kind: "case" | "customer" | "card" | "txn" | "device" | "region" | "linked_card" | "memory" | "pattern";
  label: string;
  props: Record<string, any>;
};
export type GraphData = { nodes: GraphNode[]; edges: { source: string; target: string; label: string }[] };

export type Policy = {
  version: string;
  actions: Record<string, { route?: Route; impact: string; desc: string; route_by_exposure?: any }>;
  thresholds: Record<string, number>;
  rules: { id: string; section: string; title: string; text: string }[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail ?? `${res.status} ${res.statusText}`);
  }
  return res.json();
}

export const api = {
  cases: () => request<CaseRow[]>("/api/cases"),
  stats: () => request<Stats>("/api/stats"),
  case: (id: string) => request<CaseDetail>(`/api/cases/${id}`),
  graph: (id?: string) => request<GraphData>(id ? `/api/graph/${id}` : "/api/graph"),
  policy: () => request<Policy>("/api/policy"),
  act: (id: string, action: string, role: Role) =>
    request<ActionLog>(`/api/cases/${id}/actions`, { method: "POST", body: JSON.stringify({ action, role }) }),
};

export function useApi<T>(load: () => Promise<T>, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(() => {
    setLoading(true);
    load()
      .then((d) => {
        setData(d);
        setError(null);
      })
      .catch((e: Error) => setError(e.message))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(reload, [reload]);
  return { data, error, loading, reload };
}
