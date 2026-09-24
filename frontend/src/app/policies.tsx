import { StyleSheet, Text, View } from "react-native";

import AppShell from "../components/app-shell";
import { ErrorNote, Label, Panel, RoutePill } from "../components/ui";
import { C, MONO } from "../constants/ui";
import { api, useApi } from "../lib/api";

/** Rule chunks are stored as README markdown; show them as plain prose without repeating the title. */
function clean(text: string, title: string) {
  return text
    .replace(/^Policy rule R\d+\.\s*/, "")
    .replace(/^Fraud Policy §\S+\s*[^\n]*\n/, "")
    .replace(new RegExp(`^${title.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\.?\\s*`), "")
    .replace(/\*\*|`/g, "")
    .trim();
}

export default function Policies() {
  const { data, error } = useApi(api.policy);

  return (
    <AppShell title="Policy" subtitle={data ? `Fraud Policy v${data.version} — the rules the agent operates under` : "Fraud Policy"}>
      {error ? <ErrorNote error={error} /> : null}
      {data ? (
        <View style={styles.grid}>
          <Panel title="Actions and approval routes" style={{ flex: 1, minWidth: 380 }} pad={false}>
            {Object.entries(data.actions).map(([name, a]) => (
              <View key={name} style={styles.action}>
                <View style={{ width: 64 }}>
                  {a.route ? <RoutePill route={a.route} /> : (
                    <Text style={styles.split}>L1 ≤ ${a.route_by_exposure.limit_usd.toLocaleString()}{"\n"}L2 above</Text>
                  )}
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={styles.name}>{name}</Text>
                  <Text style={styles.desc}>{a.desc}</Text>
                </View>
                <Text style={styles.impact}>{a.impact.replace("_", " ")}</Text>
              </View>
            ))}
            <Text style={styles.foot}>The agent recommends everything; it executes only auto actions. L1 and L2 wait for a human.</Text>
          </Panel>

          <View style={{ flex: 1.2, minWidth: 420, gap: 14 }}>
            <Panel title="Rules">
              <View style={{ gap: 14 }}>
                {data.rules.filter((r) => !["policy:s1", "policy:s2"].includes(r.id)).map((r) => (
                  <View key={r.id} style={styles.rule}>
                    <Label>{r.section.replace("Fraud Policy ", "")}</Label>
                    <Text style={styles.ruleTitle}>{r.title}</Text>
                    <Text style={styles.ruleText}>{clean(r.text, r.title)}</Text>
                  </View>
                ))}
                {!data.rules.length ? <Text style={styles.desc}>Rule text is served from the graph; start the TigerGraph workspace to load it.</Text> : null}
              </View>
            </Panel>
            <Panel title="Thresholds">
              {Object.entries(data.thresholds).map(([k, v]) => (
                <View key={k} style={styles.th}>
                  <Text style={styles.desc}>{k.replace(/_/g, " ")}</Text>
                  <Text style={styles.mono}>{v}</Text>
                </View>
              ))}
            </Panel>
          </View>
        </View>
      ) : null}
    </AppShell>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", gap: 14, flexWrap: "wrap", alignItems: "flex-start" },
  action: { flexDirection: "row", alignItems: "center", gap: 14, paddingHorizontal: 18, paddingVertical: 11, borderBottomWidth: 1, borderBottomColor: C.lineSoft },
  split: { fontFamily: MONO, fontSize: 10, color: C.text, lineHeight: 14 },
  name: { fontFamily: MONO, fontSize: 12.5, color: C.text, fontWeight: "600" },
  desc: { color: C.text2, fontSize: 12.5, marginTop: 2, lineHeight: 18 },
  impact: { color: C.text3, fontSize: 11.5, width: 70, textAlign: "right" },
  foot: { color: C.text3, fontSize: 12, padding: 18 },
  rule: { paddingBottom: 14, borderBottomWidth: 1, borderBottomColor: C.lineSoft, gap: 4 },
  ruleTitle: { color: C.text, fontSize: 13.5, fontWeight: "600" },
  ruleText: { color: C.text2, fontSize: 12.5, lineHeight: 19 },
  th: { flexDirection: "row", justifyContent: "space-between", paddingVertical: 5 },
  mono: { fontFamily: MONO, fontSize: 12.5, color: C.text },
});
