import { Pressable, StyleSheet, Text, View } from "react-native";
import { useRouter } from "expo-router";

import { C, humanize, MONO, TRIGGER_LABEL, usd } from "../constants/ui";
import type { CaseRow } from "../lib/api";
import { VerdictTag } from "./ui";

const COLS = [
  { key: "case", label: "Case", flex: 0.8 },
  { key: "trigger", label: "Trigger", flex: 1 },
  { key: "card", label: "Card", flex: 1 },
  { key: "verdict", label: "Verdict", flex: 1.1 },
  { key: "pattern", label: "Pattern", flex: 1.6 },
  { key: "exposure", label: "Exposure", flex: 0.9, right: true },
  { key: "status", label: "Status", flex: 1 },
  { key: "pending", label: "Approvals", flex: 0.8, right: true },
];

export default function CaseTable({ rows }: { rows: CaseRow[] }) {
  const router = useRouter();
  return (
    <View>
      <View style={[s.row, s.head]}>
        {COLS.map((c) => (
          <Text key={c.key} style={[s.th, { flex: c.flex }, c.right && { textAlign: "right" }]}>{c.label}</Text>
        ))}
      </View>
      {rows.map((r) => (
        <Pressable key={r.case_id} onPress={() => router.push(`/case/${r.case_id}` as any)}
          style={({ hovered }: any) => [s.row, s.body, hovered && { backgroundColor: "#FAFBFC" }]}>
          <Text style={[s.td, s.mono, { flex: 0.8, color: C.text }]}>{r.case_id}</Text>
          <Text style={[s.td, { flex: 1 }]}>{TRIGGER_LABEL[r.trigger_type]}</Text>
          <Text style={[s.td, s.mono, { flex: 1 }]}>{r.card_id}</Text>
          <View style={{ flex: 1.1 }}><VerdictTag verdict={r.verdict} p={r.fraud_probability} /></View>
          <Text style={[s.td, { flex: 1.6 }]} numberOfLines={1}>{humanize(r.pattern)}</Text>
          <Text style={[s.td, s.mono, { flex: 0.9, textAlign: "right" }]}>{r.exposure_usd ? usd(r.exposure_usd) : "—"}</Text>
          <Text style={[s.td, { flex: 1 }]}>{humanize(r.status)}{r.sar ? "  · SAR" : ""}</Text>
          <Text style={[s.td, s.mono, { flex: 0.8, textAlign: "right", color: r.pending_approvals ? C.text : C.text3 }]}>
            {r.pending_approvals || "—"}
          </Text>
        </Pressable>
      ))}
    </View>
  );
}

const s = StyleSheet.create({
  row: { flexDirection: "row", alignItems: "center", paddingHorizontal: 18, gap: 12 },
  head: { paddingVertical: 10, borderBottomWidth: 1, borderBottomColor: C.lineSoft },
  body: { paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: C.lineSoft },
  th: { color: C.text3, fontSize: 10.5, letterSpacing: 1, textTransform: "uppercase", fontWeight: "600" },
  td: { color: C.text2, fontSize: 13 },
  mono: { fontFamily: MONO, fontSize: 12.5 },
});
