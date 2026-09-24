import { StyleSheet, Text, View } from "react-native";

import AppShell from "../components/app-shell";
import StatCard from "../components/stat-card";

const investigations = [
  {
    id: "CASE-1042",
    customer: "Customer 2841",
    risk: "High",
    status: "Investigating",
    amount: "₹82,450",
  },
  {
    id: "CASE-1043",
    customer: "Customer 9127",
    risk: "Medium",
    status: "Review",
    amount: "₹31,200",
  },
  {
    id: "CASE-1044",
    customer: "Customer 4410",
    risk: "High",
    status: "Evidence Required",
    amount: "₹1,24,900",
  },
];

export default function Dashboard() {
  return (
    <AppShell
      title="Investigation Dashboard"
      subtitle="Monitor fraud signals and active investigations"
    >
      <View style={styles.stats}>
        <StatCard
          label="Active Investigations"
          value="24"
          change="+4 today"
        />

        <StatCard
          label="High Risk Cases"
          value="8"
          change="Requires attention"
        />

        <StatCard
          label="Transactions Flagged"
          value="147"
          change="Last 24 hours"
        />

        <StatCard
          label="Resolved Cases"
          value="312"
          change="This month"
        />
      </View>

      <View style={styles.panel}>
        <View style={styles.panelHeader}>
          <View>
            <Text style={styles.panelTitle}>
              Recent Investigations
            </Text>

            <Text style={styles.panelSubtitle}>
              Latest cases requiring analyst review
            </Text>
          </View>
        </View>

        <View style={styles.tableHeader}>
          <Text style={[styles.headerCell, styles.caseColumn]}>
            CASE
          </Text>

          <Text style={[styles.headerCell, styles.customerColumn]}>
            CUSTOMER
          </Text>

          <Text style={styles.headerCell}>AMOUNT</Text>

          <Text style={styles.headerCell}>RISK</Text>

          <Text style={styles.headerCell}>STATUS</Text>
        </View>

        {investigations.map((item) => (
          <View key={item.id} style={styles.tableRow}>
            <Text style={[styles.cell, styles.caseColumn]}>
              {item.id}
            </Text>

            <Text style={[styles.cell, styles.customerColumn]}>
              {item.customer}
            </Text>

            <Text style={styles.cell}>{item.amount}</Text>

            <Text
              style={[
                styles.cell,
                item.risk === "High"
                  ? styles.highRisk
                  : styles.mediumRisk,
              ]}
            >
              {item.risk}
            </Text>

            <Text style={styles.cell}>{item.status}</Text>
          </View>
        ))}
      </View>
    </AppShell>
  );
}

const styles = StyleSheet.create({
  stats: {
    flexDirection: "row",
    flexWrap: "wrap",
    gap: 18,
  },

  panel: {
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    marginTop: 28,
    overflow: "hidden",
  },

  panelHeader: {
    padding: 22,
    borderBottomWidth: 1,
    borderBottomColor: "#E5E7EB",
  },

  panelTitle: {
    fontSize: 18,
    fontWeight: "800",
    color: "#111827",
  },

  panelSubtitle: {
    color: "#6B7280",
    marginTop: 5,
    fontSize: 13,
  },

  tableHeader: {
    flexDirection: "row",
    paddingHorizontal: 22,
    paddingVertical: 13,
    backgroundColor: "#F9FAFB",
  },

  tableRow: {
    flexDirection: "row",
    alignItems: "center",
    paddingHorizontal: 22,
    paddingVertical: 18,
    borderTopWidth: 1,
    borderTopColor: "#F3F4F6",
  },

  headerCell: {
    flex: 1,
    color: "#6B7280",
    fontSize: 11,
    fontWeight: "700",
  },

  cell: {
    flex: 1,
    color: "#374151",
    fontSize: 13,
  },

  caseColumn: {
    flex: 0.8,
  },

  customerColumn: {
    flex: 1.3,
  },

  highRisk: {
    color: "#DC2626",
    fontWeight: "700",
  },

  mediumRisk: {
    color: "#D97706",
    fontWeight: "700",
  },
});