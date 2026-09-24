import { StyleSheet, Text, View } from "react-native";
import AppShell from "../components/app-shell";

export default function Investigations() {
  return (
    <AppShell
      title="Investigations"
      subtitle="Review and manage fraud investigation cases"
    >
      <View style={styles.card}>
        <Text style={styles.title}>Investigation Queue</Text>

        <Text style={styles.text}>
          Case management will appear here.
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