import { ReactNode } from "react";
import { Pressable, StyleSheet, Text, View, ViewStyle } from "react-native";

import { C, MONO, verdictColor, verdictSoft } from "../constants/ui";

export function Panel({ title, meta, children, style, pad = true }: {
  title?: string; meta?: ReactNode; children: ReactNode; style?: ViewStyle; pad?: boolean;
}) {
  return (
    <View style={[s.panel, style]}>
      {title ? (
        <View style={s.panelHead}>
          <Text style={s.panelTitle}>{title}</Text>
          {meta}
        </View>
      ) : null}
      <View style={pad ? s.panelBody : undefined}>{children}</View>
    </View>
  );
}

export function Label({ children }: { children: ReactNode }) {
  return <Text style={s.label}>{children}</Text>;
}

export function Mono({ children, dim, size = 12.5 }: { children: ReactNode; dim?: boolean; size?: number }) {
  return <Text style={{ fontFamily: MONO, fontSize: size, color: dim ? C.text2 : C.text }}>{children}</Text>;
}

export function VerdictTag({ verdict, p }: { verdict: string; p?: number }) {
  return (
    <View style={[s.tag, { backgroundColor: verdictSoft(verdict) }]}>
      <View style={[s.dot, { backgroundColor: verdictColor(verdict) }]} />
      <Text numberOfLines={1} style={[s.tagText, { color: verdictColor(verdict) }]}>
        {verdict}{p !== undefined ? `  ${p.toFixed(2)}` : ""}
      </Text>
    </View>
  );
}

export function RoutePill({ route }: { route: string }) {
  const auto = route === "auto";
  return (
    <View style={[s.route, auto ? s.routeAuto : s.routeHuman]}>
      <Text style={[s.routeText, { color: auto ? C.text2 : C.text }]}>{route}</Text>
    </View>
  );
}

export function Chip({ children, tone = "plain" }: { children: ReactNode; tone?: "plain" | "accent" }) {
  return (
    <View style={[s.chip, tone === "accent" && { backgroundColor: C.accentSoft, borderColor: "#D9E2FC" }]}>
      <Text style={[s.chipText, tone === "accent" && { color: C.accent }]}>{children}</Text>
    </View>
  );
}

export function Button({ label, onPress, disabled, kind = "primary" }: {
  label: string; onPress: () => void; disabled?: boolean; kind?: "primary" | "ghost";
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled}
      style={[s.btn, kind === "ghost" ? s.btnGhost : s.btnPrimary, disabled && { opacity: 0.35 }]}>
      <Text style={[s.btnText, kind === "ghost" && { color: C.text }]}>{label}</Text>
    </Pressable>
  );
}

export function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <View style={s.stat}>
      <Label>{label}</Label>
      <Text style={s.statValue}>{value}</Text>
      {note ? <Text style={s.statNote}>{note}</Text> : null}
    </View>
  );
}

export function Empty({ children }: { children: ReactNode }) {
  return <Text style={{ color: C.text3, fontSize: 13 }}>{children}</Text>;
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <Panel>
      <Text style={{ color: C.fraud, fontSize: 13 }}>Could not reach the Argus API: {error}</Text>
      <Text style={{ color: C.text2, fontSize: 12, marginTop: 6, fontFamily: MONO }}>
        .venv/bin/uvicorn api.server:app --port 8000
      </Text>
    </Panel>
  );
}

const s = StyleSheet.create({
  panel: { backgroundColor: C.panel, borderRadius: 10, borderWidth: 1, borderColor: C.line },
  panelHead: {
    flexDirection: "row", justifyContent: "space-between", alignItems: "center",
    paddingHorizontal: 18, paddingVertical: 13, borderBottomWidth: 1, borderBottomColor: C.lineSoft,
  },
  panelTitle: { color: C.text, fontSize: 13.5, fontWeight: "600" },
  panelBody: { padding: 18 },
  label: { color: C.text3, fontSize: 10.5, letterSpacing: 1, textTransform: "uppercase", fontWeight: "600" },
  tag: { flexDirection: "row", alignItems: "center", gap: 6, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 4, alignSelf: "flex-start" },
  dot: { width: 6, height: 6, borderRadius: 3 },
  tagText: { fontSize: 12, fontWeight: "600", fontFamily: MONO },
  route: { paddingHorizontal: 6, paddingVertical: 2, borderRadius: 3, borderWidth: 1, minWidth: 34, alignItems: "center" },
  routeAuto: { borderColor: C.line, backgroundColor: "#FAFBFC" },
  routeHuman: { borderColor: "#0E1116", backgroundColor: "#FFFFFF" },
  routeText: { fontSize: 10.5, fontFamily: MONO, fontWeight: "600" },
  chip: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 4, borderWidth: 1, borderColor: C.line, backgroundColor: "#FAFBFC", alignSelf: "flex-start" },
  chipText: { fontSize: 11.5, color: C.text2 },
  btn: { paddingHorizontal: 12, height: 28, borderRadius: 6, alignItems: "center", justifyContent: "center" },
  btnPrimary: { backgroundColor: C.text },
  btnGhost: { borderWidth: 1, borderColor: C.line, backgroundColor: C.panel },
  btnText: { color: "#FFFFFF", fontSize: 12, fontWeight: "600" },
  stat: { flex: 1, minWidth: 150, backgroundColor: C.panel, borderRadius: 10, borderWidth: 1, borderColor: C.line, padding: 16, gap: 8 },
  statValue: { color: C.text, fontSize: 24, fontWeight: "600", fontFamily: MONO },
  statNote: { color: C.text3, fontSize: 12 },
});
