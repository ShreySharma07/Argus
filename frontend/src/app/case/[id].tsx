import { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { useLocalSearchParams, useRouter } from "expo-router";

import AppShell from "../../components/app-shell";
import GraphCanvas from "../../components/graph-canvas";
import { Button, Chip, Empty, ErrorNote, Label, Mono, Panel, RoutePill, VerdictTag } from "../../components/ui";
import { C, humanize, MONO, TRIGGER_LABEL, usd, verdictColor } from "../../constants/ui";
import { Action, ActionLog, api, useApi } from "../../lib/api";
import { canApprove, ROLE_LABEL, useRole } from "../../lib/role";

export default function CaseScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const detail = useApi(() => api.case(id), [id]);
  const graph = useApi(() => api.graph(id), [id]);
  const d = detail.data;

  if (detail.error) {
    return <AppShell title={id}><ErrorNote error={detail.error} /></AppShell>;
  }
  if (!d) {
    return <AppShell title={id} subtitle="Loading investigation…"><View /></AppShell>;
  }

  const { row, answer } = d;
  const c = answer.case;

  return (
    <AppShell
      title={row.case_id}
      subtitle={`${TRIGGER_LABEL[row.trigger_type]} · opened ${row.opened_at} · card ${row.card_id}`}
      right={
        <Pressable onPress={() => router.push("/investigations" as any)}>
          <Text style={{ color: C.text2, fontSize: 13 }}>← All investigations</Text>
        </Pressable>
      }
    >
      <Panel>
        <Text style={styles.trigger}>“{row.trigger_text}”</Text>
      </Panel>

      <View style={styles.grid3}>
        <Panel title="Assessment" style={{ flex: 1.3 }}>
          <View style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
            <VerdictTag verdict={c.verdict} />
            <Text style={styles.big}>{c.fraud_probability.toFixed(2)}</Text>
            <Text style={styles.muted}>fraud probability</Text>
          </View>
          <ProbabilityPath path={d.probability_path} riskScore={row.risk_score} />
        </Panel>
        <Panel title="Finding" style={{ flex: 1 }}>
          <KV k="Pattern" v={humanize(c.pattern)} />
          <KV k="Exposure" v={c.exposure_usd ? usd(c.exposure_usd) : "—"} mono />
          <KV k="Affected txns" v={String(c.affected_txn_ids.length)} mono />
          <KV k="Linked cards" v={String(c.connected_card_ids.length)} mono />
        </Panel>
        <Panel title="Case" style={{ flex: 1 }}>
          <KV k="Status" v={humanize(c.status)} />
          <KV k="Report" v={answer.sar.file ? "SAR filed" : "Case only"} />
          <KV k="Graph record" v={c.written_to_graph ? c.graph_case_id : "—"} mono />
          <KV k="Agent cost" v={`${answer.tool_calls} calls · ${(answer.tokens / 1000).toFixed(1)}k tok · ${answer.latency_s}s`} mono />
        </Panel>
      </View>

      <Panel title="Summary">
        <Text style={styles.body}>{c.summary}</Text>
        {c.pattern_description ? (
          <View style={styles.callout}>
            <Label>Undocumented pattern</Label>
            <Text style={[styles.body, { marginTop: 6 }]}>{c.pattern_description}</Text>
          </View>
        ) : null}
      </Panel>

      <NextBestActions caseId={row.case_id} answer={answer} log={d.actions_log} onChange={detail.reload} />

      <View style={styles.grid2}>
        <Panel title={`Evidence · ${c.evidence.length}`} style={{ flex: 1.4 }}>
          <View style={{ gap: 14 }}>
            {c.evidence.map((e, i) => (
              <View key={i} style={styles.evidence}>
                <View style={{ flexDirection: "row", gap: 6, alignItems: "center" }}>
                  <Chip tone={e.source === "customer" ? "accent" : "plain"}>{e.source}</Chip>
                  <Mono dim size={11}>{e.ref}</Mono>
                </View>
                <Text style={[styles.body, { marginTop: 6 }]}>{e.claim}</Text>
                {e.entity_ids.length ? (
                  <Text style={styles.ids} numberOfLines={2}>{e.entity_ids.join("  ")}</Text>
                ) : null}
              </View>
            ))}
          </View>
        </Panel>
        <Panel title="Investigation timeline" style={{ flex: 1 }}>
          <View>
            {d.timeline.map((t, i) => (
              <View key={i} style={styles.step}>
                <View style={styles.stepRail}>
                  <View style={[styles.stepDot, t.node === "evidence_received" && { backgroundColor: C.accent },
                    t.node === "stop" && { backgroundColor: C.text }]} />
                  {i < d.timeline.length - 1 ? <View style={styles.stepLine} /> : null}
                </View>
                <View style={{ flex: 1, paddingBottom: 14 }}>
                  <Mono size={11.5}>{t.node.replace(/_/g, " ")}</Mono>
                  <Text style={styles.stepText} numberOfLines={4}>{t.detail}</Text>
                </View>
              </View>
            ))}
            {!d.timeline.length ? <Empty>No timeline recorded for this run.</Empty> : null}
          </View>
        </Panel>
      </View>

      <Panel title="Entity graph" meta={<Text style={styles.muted}>hover to trace · click for details</Text>} pad={false}>
        <View style={{ padding: 10 }}>
          {graph.data ? <GraphCanvas data={graph.data} height={440} focusId={c.graph_case_id || row.case_id} /> :
            <Empty>{graph.error ?? "Loading graph…"}</Empty>}
        </View>
      </Panel>

      <View style={styles.grid2}>
        <Panel title="Transactions" style={{ flex: 1 }} pad={false}>
          {d.transactions.map((t) => (
            <View key={t.id} style={styles.txn}>
              <Mono size={12}>{t.id}</Mono>
              <Text style={[styles.muted, { flex: 1 }]}>{t.ts ?? "—"}</Text>
              <Text style={styles.muted}>{t.channel ?? ""} {t.product_cd ?? ""}</Text>
              <Mono size={12}>{t.amount != null ? usd(t.amount) : "—"}</Mono>
              {t.id === row.flagged_txn_id ? <Chip>flagged</Chip> : null}
            </View>
          ))}
        </Panel>
        <Panel title={`Case memory · ${d.similar_cases.length}`} style={{ flex: 1 }}>
          <View style={{ gap: 12 }}>
            {d.similar_cases.map((m) => (
              <View key={m.id}>
                <View style={{ flexDirection: "row", gap: 8, alignItems: "center" }}>
                  <Mono size={12}>{m.id}</Mono>
                  {m.outcome ? <Text style={[styles.muted, { color: m.outcome === "cleared" ? C.legit : C.fraud }]}>{m.outcome.replace("_", " ")}</Text> : null}
                  {m.pattern ? <Text style={styles.muted}>{humanize(m.pattern)}</Text> : null}
                </View>
                {m.analyst_notes ? <Text style={styles.note} numberOfLines={3}>{m.analyst_notes}</Text> : null}
              </View>
            ))}
            {!d.similar_cases.length ? <Empty>No prior cases used.</Empty> : null}
          </View>
        </Panel>
      </View>

      <Panel title="Suspicious activity report" meta={<Text style={styles.muted}>{answer.sar.file ? "to be filed" : "not required"}</Text>}>
        <Text style={styles.body}>{answer.sar.reason}</Text>
        {answer.sar.file ? (
          <>
            <Text style={[styles.body, styles.narrative]}>{answer.sar.narrative}</Text>
            <View style={{ flexDirection: "row", gap: 24, marginTop: 14, flexWrap: "wrap" }}>
              <KV k="Amount" v={usd(answer.sar.total_amount_usd)} mono inline />
              <KV k="Activity" v={answer.sar.activity_dates.join(" → ")} mono inline />
            </View>
            <Text style={styles.ids}>{answer.sar.subjects.join("  ")}</Text>
          </>
        ) : null}
      </Panel>

      <Panel title="Stop reason">
        <Text style={styles.body}>{answer.stop_reason}</Text>
      </Panel>
    </AppShell>
  );
}

function ProbabilityPath({ path, riskScore }: { path: { round: string; verdict: string; p: number; confidence: number | null }[]; riskScore: number | null }) {
  const points = [
    ...(riskScore != null ? [{ label: "model score", p: riskScore, verdict: "", confidence: null as number | null }] : []),
    ...path.map((x) => ({ label: x.round, p: x.p, verdict: x.verdict, confidence: x.confidence })),
  ];
  if (!points.length) return null;
  return (
    <View style={{ marginTop: 18, gap: 10 }}>
      {points.map((pt, i) => (
        <View key={i} style={{ flexDirection: "row", alignItems: "center", gap: 12 }}>
          <Text style={[styles.muted, { width: 86 }]}>{pt.label}</Text>
          <View style={styles.track}>
            <View style={[styles.band, { left: "85%", width: "15%" }]} />
            <View style={[styles.band, { left: 0, width: "15%" }]} />
            <View style={[styles.marker, { left: `${pt.p * 100}%`, backgroundColor: pt.verdict ? verdictColor(pt.verdict) : C.text3 }]} />
          </View>
          <Mono size={12}>{pt.p.toFixed(2)}</Mono>
          <Text style={[styles.muted, { width: 72 }]}>{pt.confidence != null ? `conf ${pt.confidence.toFixed(2)}` : ""}</Text>
        </View>
      ))}
      <Text style={[styles.muted, { fontSize: 11 }]}>Shaded: policy §6 stop bands (≤ 0.15, ≥ 0.85). The model score is an input, not a verdict.</Text>
    </View>
  );
}

function NextBestActions({ caseId, answer, log, onChange }: {
  caseId: string; answer: any; log: ActionLog[]; onChange: () => void;
}) {
  const { role } = useRole();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const nba = answer.next_best_actions;
  const done = new Map(log.filter((l) => l.status === "executed").map((l) => [l.action, l]));

  const run = (a: Action) => {
    setBusy(a.action);
    setErr(null);
    api.act(caseId, a.action, a.route === "auto" ? "analyst" : role)
      .then(onChange)
      .catch((e: Error) => setErr(e.message))
      .finally(() => setBusy(null));
  };

  return (
    <Panel title="Next best action" meta={<Text style={styles.muted}>acting as {ROLE_LABEL[role]}</Text>}>
      <View style={styles.grid2}>
        <View style={{ flex: 1, gap: 10 }}>
          <Label>Before evidence</Label>
          {nba.initial.map((a: Action) => <ActionRow key={a.action} a={a} />)}
        </View>

        <View style={styles.bridge}>
          {answer.evidence_requests.length ? answer.evidence_requests.map((r: any, i: number) => (
            <View key={i} style={{ gap: 6 }}>
              <Label>{r.type.replace(/_/g, " ")}</Label>
              <Text style={styles.reply}>{r.assumed_response}</Text>
            </View>
          )) : <Text style={styles.muted}>No evidence requested: the graph evidence was decisive.</Text>}
          {nba.what_changed && nba.what_changed !== "nothing" ? (
            <View style={{ gap: 6, marginTop: 12 }}>
              <Label>What changed</Label>
              <Text style={styles.bodySmall}>{nba.what_changed}</Text>
            </View>
          ) : null}
        </View>

        <View style={{ flex: 1, gap: 10 }}>
          <Label>After evidence</Label>
          {nba.final.map((a: Action) => {
            const executed = done.get(a.action);
            const allowed = canApprove(role, a.route);
            return (
              <ActionRow key={a.action} a={a}
                right={executed ? (
                  <Text style={styles.done}>✓ {executed.actor_label}</Text>
                ) : (
                  <Button kind={a.route === "auto" ? "ghost" : "primary"} disabled={!allowed || busy === a.action}
                    label={a.route === "auto" ? "Execute" : allowed ? "Approve" : `Needs ${a.route}`}
                    onPress={() => run(a)} />
                )}
                footer={executed ? <Text style={styles.effect}>{executed.effect}</Text> : null}
              />
            );
          })}
          {err ? <Text style={{ color: C.fraud, fontSize: 12 }}>{err}</Text> : null}
        </View>
      </View>
    </Panel>
  );
}

function ActionRow({ a, right, footer }: { a: Action; right?: React.ReactNode; footer?: React.ReactNode }) {
  return (
    <View style={styles.action}>
      <View style={{ flexDirection: "row", alignItems: "center", gap: 10 }}>
        <RoutePill route={a.route} />
        <Text style={styles.actionName}>{a.action}</Text>
        <View style={{ flex: 1 }} />
        {right}
      </View>
      <Text style={styles.reason}>{a.reason}</Text>
      {footer}
    </View>
  );
}

function KV({ k, v, mono, inline }: { k: string; v: string; mono?: boolean; inline?: boolean }) {
  return (
    <View style={inline ? { gap: 4 } : styles.kv}>
      <Text style={styles.kvKey}>{k}</Text>
      <Text style={[styles.kvVal, mono && { fontFamily: MONO, fontSize: 12.5 }]}>{v}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  trigger: { color: C.text, fontSize: 14, lineHeight: 21 },
  grid3: { flexDirection: "row", gap: 14, flexWrap: "wrap" },
  grid2: { flexDirection: "row", gap: 14, flexWrap: "wrap" },
  big: { fontFamily: MONO, fontSize: 26, color: C.text, fontWeight: "600" },
  muted: { color: C.text3, fontSize: 12 },
  body: { color: C.text, fontSize: 13.5, lineHeight: 21 },
  bodySmall: { color: C.text2, fontSize: 12.5, lineHeight: 19 },
  callout: { marginTop: 14, padding: 14, borderRadius: 8, backgroundColor: C.fraudSoft },
  track: { flex: 1, height: 6, borderRadius: 3, backgroundColor: C.lineSoft, position: "relative" },
  band: { position: "absolute", top: 0, height: 6, backgroundColor: "#E3E6EB", borderRadius: 3 },
  marker: { position: "absolute", top: -4, width: 14, height: 14, marginLeft: -7, borderRadius: 7, borderWidth: 2, borderColor: "#FFFFFF" },
  kv: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 6, borderBottomWidth: 1, borderBottomColor: C.lineSoft, gap: 10 },
  kvKey: { color: C.text3, fontSize: 12.5 },
  kvVal: { color: C.text, fontSize: 13, textAlign: "right", flexShrink: 1 },
  bridge: { flex: 0.9, minWidth: 220, borderLeftWidth: 1, borderRightWidth: 1, borderColor: C.lineSoft, paddingHorizontal: 18, gap: 12 },
  reply: { color: C.text, fontSize: 13, lineHeight: 20, fontStyle: "italic" },
  action: { borderWidth: 1, borderColor: C.lineSoft, borderRadius: 8, padding: 11, gap: 6 },
  actionName: { fontFamily: MONO, fontSize: 12.5, color: C.text, fontWeight: "600" },
  reason: { color: C.text2, fontSize: 12, lineHeight: 17 },
  done: { color: C.legit, fontSize: 12, fontFamily: MONO },
  effect: { color: C.legit, fontSize: 11.5, fontFamily: MONO },
  evidence: { paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: C.lineSoft },
  ids: { color: C.text3, fontFamily: MONO, fontSize: 11, marginTop: 6 },
  step: { flexDirection: "row", gap: 12 },
  stepRail: { width: 10, alignItems: "center" },
  stepDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: "#C3C8D0", marginTop: 4 },
  stepLine: { flex: 1, width: 1, backgroundColor: C.line, marginTop: 4 },
  stepText: { color: C.text2, fontSize: 12, lineHeight: 17, marginTop: 3 },
  txn: { flexDirection: "row", alignItems: "center", gap: 12, paddingHorizontal: 18, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: C.lineSoft },
  note: { color: C.text2, fontSize: 12, lineHeight: 17, marginTop: 4 },
  narrative: { marginTop: 14, padding: 16, backgroundColor: "#FAFBFC", borderRadius: 8, borderWidth: 1, borderColor: C.lineSoft },
});
