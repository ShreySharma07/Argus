import { useMemo, useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import AppShell from "../components/app-shell";
import CaseTable from "../components/case-table";
import { ErrorNote, Panel } from "../components/ui";
import { C } from "../constants/ui";
import { api, useApi } from "../lib/api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "fraud", label: "Fraud" },
  { key: "legitimate", label: "Legitimate" },
  { key: "uncertain", label: "Uncertain" },
  { key: "pending", label: "Awaiting approval" },
  { key: "sar", label: "SAR filed" },
];

export default function Investigations() {
  const { data, error } = useApi(api.cases);
  const [filter, setFilter] = useState("all");
  const rows = useMemo(() => (data ?? []).filter((r) =>
    filter === "all" ? true : filter === "pending" ? r.pending_approvals > 0 : filter === "sar" ? r.sar : r.verdict === filter,
  ), [data, filter]);

  return (
    <AppShell title="Investigations" subtitle="Every alert the agent investigated, with its outcome and open approvals">
      {error ? <ErrorNote error={error} /> : null}
      <View style={styles.filters}>
        {FILTERS.map((f) => (
          <Pressable key={f.key} onPress={() => setFilter(f.key)} style={[styles.filter, filter === f.key && styles.filterOn]}>
            <Text style={[styles.filterText, filter === f.key && styles.filterTextOn]}>{f.label}</Text>
          </Pressable>
        ))}
      </View>
      <Panel pad={false}>
        <CaseTable rows={rows} />
        {data && rows.length === 0 ? <Text style={styles.none}>No cases match this filter.</Text> : null}
      </Panel>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  filters: { flexDirection: "row", gap: 6, flexWrap: "wrap" },
  filter: { paddingHorizontal: 11, height: 28, borderRadius: 14, borderWidth: 1, borderColor: C.line, justifyContent: "center", backgroundColor: C.panel },
  filterOn: { backgroundColor: C.text, borderColor: C.text },
  filterText: { fontSize: 12.5, color: C.text2 },
  filterTextOn: { color: "#FFFFFF" },
  none: { padding: 18, color: C.text3, fontSize: 13 },
});
