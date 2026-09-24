import { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";
import { usePathname, useRouter } from "expo-router";

import { C, MONO } from "../constants/ui";
import type { Role } from "../lib/api";
import { ROLE_LABEL, useRole } from "../lib/role";

type Props = {
  children: ReactNode;
  title: string;
  subtitle?: string;
  right?: ReactNode;
  bleed?: boolean; // full-width content without padding (graph canvas)
};

const navigation = [
  { label: "Overview", href: "/" },
  { label: "Investigations", href: "/investigations" },
  { label: "Knowledge Graph", href: "/knowledge-graph" },
  { label: "Policy", href: "/policies" },
];

const ROLES: Role[] = ["analyst", "L1", "L2"];

export default function AppShell({ children, title, subtitle, right, bleed }: Props) {
  const router = useRouter();
  const pathname = usePathname();
  const { role, setRole } = useRole();

  return (
    <View style={styles.container}>
      <View style={styles.sidebar}>
        <View style={styles.brandRow}>
          <View style={styles.mark} />
          <Text style={styles.brand}>ARGUS</Text>
        </View>
        <Text style={styles.brandSub}>Fraud investigation</Text>

        <View style={styles.nav}>
          {navigation.map((item) => {
            const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href) ||
              (item.href === "/investigations" && pathname.startsWith("/case"));
            return (
              <Pressable key={item.href} onPress={() => router.push(item.href as any)}
                style={[styles.navItem, active && styles.navItemActive]}>
                <View style={[styles.navBar, active && styles.navBarActive]} />
                <Text style={[styles.navText, active && styles.navTextActive]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>

        <View style={styles.roleBox}>
          <Text style={styles.roleHeading}>Acting as</Text>
          {ROLES.map((r) => (
            <Pressable key={r} onPress={() => setRole(r)} style={styles.roleRow}>
              <View style={[styles.radio, role === r && styles.radioOn]} />
              <Text style={[styles.roleText, role === r && styles.roleTextOn]}>{ROLE_LABEL[r]}</Text>
            </Pressable>
          ))}
          <Text style={styles.roleHint}>L1 and L2 actions need an approver with that authority.</Text>
        </View>
      </View>

      <View style={styles.main}>
        <View style={styles.header}>
          <View style={{ flexShrink: 1 }}>
            <Text style={styles.title}>{title}</Text>
            {subtitle ? <Text style={styles.subtitle}>{subtitle}</Text> : null}
          </View>
          {right}
        </View>
        {bleed ? (
          <View style={{ flex: 1 }}>{children}</View>
        ) : (
          <ScrollView style={{ flex: 1 }} contentContainerStyle={styles.content}>
            {children}
          </ScrollView>
        )}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, minHeight: "100%", flexDirection: "row", backgroundColor: C.bg },
  sidebar: { width: 232, backgroundColor: C.sidebar, paddingHorizontal: 18, paddingVertical: 22 },
  brandRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  mark: { width: 14, height: 14, borderRadius: 3, borderWidth: 2, borderColor: "#E6E8EC", transform: [{ rotate: "45deg" }] },
  brand: { color: "#F4F5F7", fontSize: 15, fontWeight: "700", letterSpacing: 3 },
  brandSub: { color: C.sidebarText, fontSize: 11, marginTop: 6, marginLeft: 24 },
  nav: { marginTop: 36, gap: 2 },
  navItem: { height: 38, flexDirection: "row", alignItems: "center", borderRadius: 6, paddingRight: 10 },
  navItemActive: { backgroundColor: "#151A22" },
  navBar: { width: 2, height: 16, marginRight: 12, backgroundColor: "transparent", borderRadius: 1 },
  navBarActive: { backgroundColor: "#E6E8EC" },
  navText: { color: C.sidebarText, fontSize: 13.5, fontWeight: "500" },
  navTextActive: { color: "#F4F5F7" },
  roleBox: { marginTop: "auto", borderTopWidth: 1, borderTopColor: C.sidebarLine, paddingTop: 16, gap: 8 },
  roleHeading: { color: "#5E6675", fontSize: 10.5, letterSpacing: 1.2, textTransform: "uppercase", marginBottom: 2 },
  roleRow: { flexDirection: "row", alignItems: "center", gap: 10, paddingVertical: 3 },
  radio: { width: 10, height: 10, borderRadius: 5, borderWidth: 1.5, borderColor: "#4A5160" },
  radioOn: { borderColor: "#E6E8EC", backgroundColor: "#E6E8EC" },
  roleText: { color: C.sidebarText, fontSize: 12.5 },
  roleTextOn: { color: "#F4F5F7" },
  roleHint: { color: "#4F5664", fontSize: 10.5, lineHeight: 15, marginTop: 6, fontFamily: MONO },
  main: { flex: 1 },
  header: {
    minHeight: 76, paddingHorizontal: 32, paddingVertical: 16, backgroundColor: C.panel,
    borderBottomWidth: 1, borderBottomColor: C.line, flexDirection: "row", alignItems: "center",
    justifyContent: "space-between", gap: 16,
  },
  title: { color: C.text, fontSize: 19, fontWeight: "650" as any },
  subtitle: { color: C.text2, marginTop: 4, fontSize: 13 },
  content: { padding: 28, gap: 20, maxWidth: 1280, width: "100%" },
});
