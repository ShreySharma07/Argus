import { StyleSheet, Text, View } from "react-native";
import AppShell from "../components/app-shell";

export default function Policies() {
  return (
    <AppShell
      title="Policies"
      subtitle="Fraud policies, regulations and investigation rules"
    >
      <View style={styles.card}>
        <Text style={styles.title}>
          Policy Knowledge Base
        </Text>

        <Text style={styles.text}>
          Fraud policies and regulatory information will appear here.
        </Text>
      </View>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: "#FFFFFF",
    padding: 24,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#E5E7EB",
  },

  title: {
    color: "#111827",
    fontSize: 20,
    fontWeight: "800",
  },

  text: {
    color: "#6B7280",
    marginTop: 8,
  },
});