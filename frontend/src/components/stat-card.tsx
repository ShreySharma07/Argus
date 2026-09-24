import { StyleSheet, Text, View } from "react-native";

type Props = {
  label: string;
  value: string;
  change?: string;
};

export default function StatCard({
  label,
  value,
  change,
}: Props) {
  return (
    <View style={styles.card}>
      <Text style={styles.label}>{label}</Text>

      <Text style={styles.value}>{value}</Text>

      {change ? (
        <Text style={styles.change}>{change}</Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    flex: 1,
    minWidth: 180,
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    padding: 22,
    borderWidth: 1,
    borderColor: "#E5E7EB",
  },

  label: {
    color: "#6B7280",
    fontSize: 13,
    fontWeight: "600",
  },

  value: {
    color: "#111827",
    fontSize: 30,
    fontWeight: "800",
    marginTop: 10,
  },

  change: {
    color: "#2563EB",
    fontSize: 12,
    marginTop: 8,
  },
});