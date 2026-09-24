import { StyleSheet, Text, View } from "react-native";

import AppShell from "../components/app-shell";
import CaseTable from "../components/case-table";
import { ErrorNote, Panel, Stat } from "../components/ui";
import { C, humanize, MONO, usd } from "../constants/ui";
import { api, useApi } from "../lib/api";

export default function Overview() {
  const stats = useApi(api.stats);
  const cases = useApi(api.cases);
  const s = stats.data;

  return (
    <AppShell title="Overview" subtitle="Benchmark case pack · November–December 2016">
      {stats.error ? <ErrorNote error={stats.error} /> : null}
      {s ? (
        <View style={styles.stats}>
          <Stat label="Cases investigated" value={String(s.cases)}
            note={`${s.evidence_requests} evidence requests · ${s.avg_latency_s}s avg`} />
          <Stat label="Fraud" value={String(s.verdicts.fraud ?? 0)}
            note={`${s.verdicts.legitimate ?? 0} legitimate · ${s.verdicts.uncertain ?? 0} uncertain`} />
          <Stat label="Exposure" value={usd(s.exposure_usd)} note={`${s.sars} suspicious activity reports`} />
          <Stat label="Awaiting approval" value={String(s.pending_approvals)} note="L1 / L2 actions" />
        </View>
      ) : null}

      {s ? (
        <Panel title="Patterns identified">
          <View style={styles.bars}>
            {Object.entries(s.patterns).sort((a, b) => b[1] - a[1]).map(([p, n]) => (
              <View key={p} style={styles.barRow}>
                <Text style={styles.barLabel}>{p === "none" ? "legitimate (no pattern)" : humanize(p)}</Text>
                <View style={styles.barTrack}>
                  <View style={[styles.barFill, { width: `${(n / s.cases) * 100}%`,
                    backgroundColor: p === "none" ? "#C9CED6" : p === "undocumented" ? C.fraud : C.text }]} />
                </View>
                <Text style={styles.barValue}>{n}</Text>
              </View>
            ))}
          </View>
        </Panel>
      ) : null}

      <Panel title="Case queue" pad={false}>
        {cases.data ? <CaseTable rows={cases.data} /> : null}
      </Panel>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  stats: { flexDirection: "row", flexWrap: "wrap", gap: 14 },
  bars: { gap: 10 },
  barRow: { flexDirection: "row", alignItems: "center", gap: 14 },
  barLabel: { width: 220, color: C.text2, fontSize: 13 },
  barTrack: { flex: 1, height: 6, backgroundColor: C.lineSoft, borderRadius: 3, overflow: "hidden" },
  barFill: { height: 6, borderRadius: 3 },
  barValue: { width: 28, textAlign: "right", fontFamily: MONO, fontSize: 12.5, color: C.text },
});
