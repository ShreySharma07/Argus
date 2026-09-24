import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import AppShell from "../components/app-shell";
import GraphCanvas from "../components/graph-canvas";
import { ErrorNote } from "../components/ui";
import { C, MONO, verdictColor } from "../constants/ui";
import { api, useApi } from "../lib/api";

export default function KnowledgeGraph() {
  const router = useRouter();
  const cases = useApi(api.cases);
  const [focus, setFocus] = useState<string | undefined>(undefined);
  const graph = useApi(() => api.graph(focus), [focus]);

  return (
    <AppShell title="Knowledge Graph"
      subtitle={focus ? `${focus} — its card, transactions, devices, linked cards and case memory`
        : "All investigations, joined by the patterns, devices, cards and prior cases they share"}>
      {graph.error ? <ErrorNote error={graph.error} /> : null}
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.picker}>
        <Pressable onPress={() => setFocus(undefined)} style={[styles.pick, !focus && styles.pickOn]}>
          <Text style={[styles.pickText, !focus && styles.pickTextOn]}>All cases</Text>
        </Pressable>
        {(cases.data ?? []).map((r) => (
          <Pressable key={r.case_id} onPress={() => setFocus(r.case_id)} style={[styles.pick, focus === r.case_id && styles.pickOn]}>
            <View style={[styles.dot, { backgroundColor: verdictColor(r.verdict) }]} />
            <Text style={[styles.pickText, focus === r.case_id && styles.pickTextOn]}>{r.case_id.replace("HHG-", "")}</Text>
          </Pressable>
        ))}
      </ScrollView>
      {graph.data ? (
        <GraphCanvas data={graph.data} height={640} focusId={focus ? `AC-${focus}` : undefined}
          onOpenCase={(id) => router.push(`/case/${id}` as any)} />
      ) : (
        <View style={styles.loading}><Text style={styles.loadingText}>Building graph…</Text></View>
      )}
      {graph.data ? (
        <Text style={styles.meta}>
          {graph.data.nodes.length} entities · {graph.data.edges.length} relationships · served from TigerGraph
          {!focus ? " · double-click a case to open it" : ""}
        </Text>
      ) : null}
    </AppShell>
  );
}

const styles = StyleSheet.create({
  picker: { gap: 6, paddingBottom: 2 },
  pick: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 10, height: 28, borderRadius: 14, borderWidth: 1, borderColor: C.line, backgroundColor: C.panel },
  pickOn: { backgroundColor: C.text, borderColor: C.text },
  pickText: { fontSize: 12, color: C.text2, fontFamily: MONO },
  pickTextOn: { color: "#FFFFFF" },
  dot: { width: 6, height: 6, borderRadius: 3 },
  loading: { height: 640, borderRadius: 10, backgroundColor: "#05070C", alignItems: "center", justifyContent: "center" },
  loadingText: { color: "#5E6A7F", fontFamily: MONO, fontSize: 12 },
  meta: { color: C.text3, fontSize: 12, fontFamily: MONO },
});
