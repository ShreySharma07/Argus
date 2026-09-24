import { ReactNode } from "react";
import {
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { usePathname, useRouter } from "expo-router";

type Props = {
  children: ReactNode;
  title: string;
  subtitle?: string;
};

const navigation = [
  {
    label: "Dashboard",
    href: "/",
    icon: "▦",
  },
  {
    label: "Investigations",
    href: "/investigations",
    icon: "⌕",
  },
  {
    label: "Knowledge Graph",
    href: "/knowledge-graph",
    icon: "◉",
  },
  {
    label: "Policies",
    href: "/policies",
    icon: "☷",
  },
];

export default function AppShell({
  children,
  title,
  subtitle,
}: Props) {
  const router = useRouter();
  const pathname = usePathname();

  return (
    <View style={styles.container}>
      <View style={styles.sidebar}>
        <View style={styles.logoContainer}>
          <View style={styles.logo}>
            <Text style={styles.logoLetter}>A</Text>
          </View>

          <View>
            <Text style={styles.brand}>ARGUS</Text>
            <Text style={styles.brandSubtitle}>Fraud Intelligence</Text>
          </View>
        </View>

        <View style={styles.navigation}>
          {navigation.map((item) => {
            const active = pathname === item.href;

            return (
              <Pressable
                key={item.href}
                onPress={() => router.push(item.href as any)}
                style={[
                  styles.navItem,
                  active && styles.navItemActive,
                ]}
              >
                <Text
                  style={[
                    styles.navIcon,
                    active && styles.navTextActive,
                  ]}
                >
                  {item.icon}
                </Text>

                <Text
                  style={[
                    styles.navText,
                    active && styles.navTextActive,
                  ]}
                >
                  {item.label}
                </Text>
              </Pressable>
            );
          })}
        </View>

        <View style={styles.sidebarBottom}>
          <View style={styles.avatar}>
            <Text style={styles.avatarText}>AB</Text>
          </View>

          <View>
            <Text style={styles.userName}>Analyst</Text>
            <Text style={styles.userRole}>Investigation Team</Text>
          </View>
        </View>
      </View>

      <View style={styles.main}>
        <View style={styles.header}>
          <View>
            <Text style={styles.pageTitle}>{title}</Text>

            {subtitle ? (
              <Text style={styles.pageSubtitle}>{subtitle}</Text>
            ) : null}
          </View>

          <View style={styles.systemStatus}>
            <View style={styles.statusDot} />
            <Text style={styles.statusText}>System Operational</Text>
          </View>
        </View>

        <View style={styles.content}>{children}</View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    minHeight: "100%",
    flexDirection: "row",
    backgroundColor: "#F4F7FB",
  },

  sidebar: {
    width: 250,
    backgroundColor: "#111827",
    paddingHorizontal: 20,
    paddingVertical: 24,
  },

  logoContainer: {
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
    marginBottom: 40,
  },

  logo: {
    width: 42,
    height: 42,
    borderRadius: 12,
    backgroundColor: "#2563EB",
    alignItems: "center",
    justifyContent: "center",
  },

  logoLetter: {
    color: "white",
    fontSize: 22,
    fontWeight: "800",
  },

  brand: {
    color: "white",
    fontSize: 18,
    fontWeight: "800",
    letterSpacing: 1,
  },

  brandSubtitle: {
    color: "#9CA3AF",
    fontSize: 11,
    marginTop: 2,
  },

  navigation: {
    gap: 8,
  },

  navItem: {
    height: 48,
    borderRadius: 10,
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 14,
    gap: 14,
  },

  navItemActive: {
    backgroundColor: "#1F2937",
  },

  navIcon: {
    width: 22,
    color: "#9CA3AF",
    fontSize: 20,
  },

  navText: {
    color: "#9CA3AF",
    fontSize: 15,
    fontWeight: "600",
  },

  navTextActive: {
    color: "#FFFFFF",
  },

  sidebarBottom: {
    marginTop: "auto",
    borderTopWidth: 1,
    borderTopColor: "#374151",
    paddingTop: 20,
    flexDirection: "row",
    alignItems: "center",
    gap: 12,
  },

  avatar: {
    width: 38,
    height: 38,
    borderRadius: 19,
    backgroundColor: "#2563EB",
    alignItems: "center",
    justifyContent: "center",
  },

  avatarText: {
    color: "white",
    fontWeight: "700",
  },

  userName: {
    color: "white",
    fontWeight: "700",
  },

  userRole: {
    color: "#9CA3AF",
    fontSize: 11,
    marginTop: 2,
  },

  main: {
    flex: 1,
  },

  header: {
    height: 92,
    backgroundColor: "#FFFFFF",
    borderBottomWidth: 1,
    borderBottomColor: "#E5E7EB",
    paddingHorizontal: 32,
    flexDirection: "row",
    alignItems: "center",
    justifyContent: "space-between",
  },

  pageTitle: {
    color: "#111827",
    fontSize: 24,
    fontWeight: "800",
  },

  pageSubtitle: {
    color: "#6B7280",
    marginTop: 5,
  },

  systemStatus: {
    flexDirection: "row",
    alignItems: "center",
    gap: 7,
  },

  statusDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: "#22C55E",
  },

  statusText: {
    color: "#4B5563",
    fontSize: 13,
  },

  content: {
    flex: 1,
    padding: 32,
  },
});