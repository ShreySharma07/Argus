import React, { useMemo, useState } from "react";
import {
  Platform,
  StyleSheet,
  Text,
  View,
} from "react-native";
import AppShell from "../components/app-shell";

import Svg, {
  Circle,
  G,
  Line,
  Text as SvgText,
} from "react-native-svg";

import {
  forceCenter,
  forceCollide,
  forceLink,
  forceManyBody,
  forceSimulation,
  SimulationLinkDatum,
  SimulationNodeDatum,
} from "d3-force";

/* ================= GRAPH SIZE ================= */

const GRAPH_WIDTH = 850;
const GRAPH_HEIGHT = 570;

/* ================= TYPES ================= */

type NodeType =
  | "customer"
  | "card"
  | "transaction"
  | "device"
  | "ip";

type GraphNode = {
  id: string;
  type: NodeType;
  label: string;
  value: string;

  details: {
    [key: string]: string;
  };
};

/*
  D3 adds things such as:
  x
  y
  vx
  vy
*/
type PositionedNode = GraphNode &
  SimulationNodeDatum & {
    x: number;
    y: number;
  };

type GraphEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
};

type SimulationEdge =
  SimulationLinkDatum<PositionedNode> & {
    id: string;
    label: string;
  };

/* ================= NODES ================= */

/*
  Notice:
  NO x
  NO y

  D3 will calculate them.
*/

const nodes: GraphNode[] = [
  {
    id: "customer-1",
    type: "customer",
    label: "Customer",
    value: "C-1001",

    details: {
      Name: "Rahul Sharma",
      Risk: "High",
      Location: "Delhi",
      AccountAge: "3 years",
    },
  },

  {
    id: "card-1",
    type: "card",
    label: "Card",
    value: "**** 7821",

    details: {
      CardType: "Credit Card",
      Bank: "ABC Bank",
      Status: "Active",
      Limit: "₹2,00,000",
    },
  },

  {
    id: "transaction-1",
    type: "transaction",
    label: "Transaction",
    value: "₹82,450",

    details: {
      Amount: "₹82,450",
      Merchant: "Electronics Store",
      Status: "Flagged",
      Time: "14:32",
    },
  },

  {
    id: "device-1",
    type: "device",
    label: "Device",
    value: "DEV-204",

    details: {
      DeviceType: "Android",
      OS: "Android 14",
      Trusted: "No",
      FirstSeen: "Today",
    },
  },

  {
    id: "ip-1",
    type: "ip",
    label: "IP",
    value: "192.168.x.x",

    details: {
      Country: "India",
      City: "Delhi",
      VPN: "Possible",
      RiskLevel: "Medium",
    },
  },
];

/* ================= EDGES ================= */

const edges: GraphEdge[] = [
  {
    id: "edge-1",
    source: "customer-1",
    target: "card-1",
    label: "OWNS",
  },

  {
    id: "edge-2",
    source: "card-1",
    target: "transaction-1",
    label: "MADE",
  },

  {
    id: "edge-3",
    source: "transaction-1",
    target: "device-1",
    label: "USED DEVICE",
  },

  {
    id: "edge-4",
    source: "transaction-1",
    target: "ip-1",
    label: "FROM IP",
  },
];

/* ================= COLORS ================= */

const nodeColors: Record<NodeType, string> = {
  customer: "#2563EB",
  card: "#7C3AED",
  transaction: "#DC2626",
  device: "#059669",
  ip: "#D97706",
};

export default function KnowledgeGraph() {
  const [selectedNode, setSelectedNode] =
    useState<GraphNode | null>(null);

  /* ================= D3 FORCE LAYOUT ================= */

  const positionedNodes = useMemo(() => {
    /*
      Give nodes simple initial positions.

      These are only starting positions.
      D3 will rearrange everything.
    */

    const simulationNodes: PositionedNode[] =
      nodes.map((node, index) => {
        const angle =
          (index / nodes.length) * Math.PI * 2;

        return {
          ...node,

          x:
            GRAPH_WIDTH / 2 +
            Math.cos(angle) * 180,

          y:
            GRAPH_HEIGHT / 2 +
            Math.sin(angle) * 180,
        };
      });

    /*
      D3 changes source/target internally,
      so create a separate copy.
    */

    const simulationEdges: SimulationEdge[] =
      edges.map((edge) => ({
        id: edge.id,
        source: edge.source,
        target: edge.target,
        label: edge.label,
      }));

    const simulation =
      forceSimulation<PositionedNode>(
        simulationNodes
      )

        /*
          Connected nodes should stay
          reasonably close together.
        */
        .force(
          "link",
          forceLink<
            PositionedNode,
            SimulationEdge
          >(simulationEdges)
            .id((node) => node.id)
            .distance(150)
            .strength(0.8)
        )

        /*
          Nodes repel each other.
        */
        .force(
          "charge",
          forceManyBody().strength(-700)
        )

        /*
          Keep the whole graph centered.
        */
        .force(
          "center",
          forceCenter(
            GRAPH_WIDTH / 2,
            GRAPH_HEIGHT / 2
          )
        )

        /*
          Prevent circles overlapping.
        */
        .force(
          "collision",
          forceCollide<PositionedNode>(65)
        )

        .stop();

    /*
      Normally D3 can animate continuously.

      For now we're calculating the final
      positions immediately.
    */

    for (let i = 0; i < 250; i++) {
      simulation.tick();
    }

    /*
      Prevent nodes escaping outside
      our SVG area.
    */

    return simulationNodes.map((node) => ({
      ...node,

      x: Math.max(
        60,
        Math.min(
          GRAPH_WIDTH - 60,
          node.x ?? GRAPH_WIDTH / 2
        )
      ),

      y: Math.max(
        60,
        Math.min(
          GRAPH_HEIGHT - 60,
          node.y ?? GRAPH_HEIGHT / 2
        )
      ),
    }));
  }, []);

  return (
    <AppShell
      title="Knowledge Graph"
      subtitle="Explore relationships between customers, transactions and fraud signals"
    >
      <View style={styles.container}>
        {/* ================= TOOLBAR ================= */}

        <View style={styles.toolbar}>
          <View>
            <Text style={styles.title}>
              Entity Network
            </Text>

            <Text style={styles.subtitle}>
              Select any entity to inspect its
              properties
            </Text>
          </View>
        </View>

        <View style={styles.content}>
          {/* ================= GRAPH ================= */}

          <View style={styles.graphArea}>
            <Svg
              width="100%"
              height={GRAPH_HEIGHT}
              viewBox={`0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}`}
            >
              {/* ================= EDGES ================= */}

              {edges.map((edge) => {
                const sourceNode =
                  positionedNodes.find(
                    (node) =>
                      node.id === edge.source
                  );

                const targetNode =
                  positionedNodes.find(
                    (node) =>
                      node.id === edge.target
                  );

                if (
                  !sourceNode ||
                  !targetNode
                ) {
                  return null;
                }

                const labelX =
                  (sourceNode.x +
                    targetNode.x) /
                  2;

                const labelY =
                  (sourceNode.y +
                    targetNode.y) /
                  2;

                return (
                  <React.Fragment
                    key={edge.id}
                  >
                    <Line
                      x1={sourceNode.x}
                      y1={sourceNode.y}
                      x2={targetNode.x}
                      y2={targetNode.y}
                      stroke="#CBD5E1"
                      strokeWidth={3}
                    />

                    <SvgText
                      x={labelX}
                      y={labelY - 8}
                      textAnchor="middle"
                      fill="#64748B"
                      fontSize={11}
                      fontWeight="600"
                    >
                      {edge.label}
                    </SvgText>
                  </React.Fragment>
                );
              })}

              {/* ================= NODES ================= */}

         {positionedNodes.map((node) => {
  const isSelected =
    selectedNode?.id === node.id;

  const circle = (
    <>
      <Circle
        cx={node.x}
        cy={node.y}
        r={48}
        fill={nodeColors[node.type]}
        stroke={
          isSelected
            ? "#111827"
            : "#FFFFFF"
        }
        strokeWidth={
          isSelected ? 5 : 2
        }
      />

      <SvgText
        x={node.x}
        y={node.y - 4}
        textAnchor="middle"
        fill="#FFFFFF"
        fontSize={12}
        fontWeight="bold"
        pointerEvents="none"
      >
        {node.label}
      </SvgText>

      <SvgText
        x={node.x}
        y={node.y + 16}
        textAnchor="middle"
        fill="#FFFFFF"
        fontSize={10}
        pointerEvents="none"
      >
        {node.value}
      </SvgText>
    </>
  );

  if (Platform.OS === "web") {
    return (
      <g
        key={node.id}
        onClick={() =>
          setSelectedNode(node)
        }
        style={{
          cursor: "pointer",
        }}
      >
        {circle}
      </g>
    );
  }

  return (
    <G
      key={node.id}
      onPress={() =>
        setSelectedNode(node)
      }
    >
      {circle}
    </G>
  );
})}
            </Svg>
          </View>

          {/* ================= DETAILS PANEL ================= */}

          <View style={styles.detailsPanel}>
            {selectedNode ? (
              <>
                <Text
                  style={
                    styles.detailsHeading
                  }
                >
                  Entity Details
                </Text>

                <View
                  style={[
                    styles.entityBadge,
                    {
                      backgroundColor:
                        nodeColors[
                          selectedNode.type
                        ],
                    },
                  ]}
                >
                  <Text
                    style={
                      styles.entityBadgeText
                    }
                  >
                    {selectedNode.label}
                  </Text>
                </View>

                <View style={styles.basicInfo}>
                  <Text style={styles.infoLabel}>
                    Entity ID
                  </Text>

                  <Text style={styles.infoValue}>
                    {selectedNode.id}
                  </Text>
                </View>

                <View style={styles.basicInfo}>
                  <Text style={styles.infoLabel}>
                    Type
                  </Text>

                  <Text style={styles.infoValue}>
                    {selectedNode.type}
                  </Text>
                </View>

                <View style={styles.basicInfo}>
                  <Text style={styles.infoLabel}>
                    Value
                  </Text>

                  <Text style={styles.infoValue}>
                    {selectedNode.value}
                  </Text>
                </View>

                <View style={styles.divider} />

                <Text
                  style={
                    styles.propertiesTitle
                  }
                >
                  Properties
                </Text>

                {Object.entries(
                  selectedNode.details
                ).map(([key, value]) => (
                  <View
                    key={key}
                    style={
                      styles.propertyRow
                    }
                  >
                    <Text
                      style={
                        styles.propertyKey
                      }
                    >
                      {key}
                    </Text>

                    <Text
                      style={
                        styles.propertyValue
                      }
                    >
                      {value}
                    </Text>
                  </View>
                ))}
              </>
            ) : (
              <View style={styles.emptyDetails}>
                <Text style={styles.emptyIcon}>
                  ◎
                </Text>

                <Text style={styles.emptyTitle}>
                  Select an entity
                </Text>

                <Text
                  style={
                    styles.emptyDescription
                  }
                >
                  Click a node to inspect its
                  information.
                </Text>
              </View>
            )}
          </View>
        </View>
      </View>
    </AppShell>
  );
}

/* ================= STYLES ================= */

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: "#FFFFFF",
    borderRadius: 14,
    borderWidth: 1,
    borderColor: "#E5E7EB",
    overflow: "hidden",
  },

  toolbar: {
    padding: 22,
    borderBottomWidth: 1,
    borderBottomColor: "#E5E7EB",
  },

  title: {
    fontSize: 18,
    fontWeight: "800",
    color: "#111827",
  },

  subtitle: {
    color: "#6B7280",
    fontSize: 13,
    marginTop: 5,
  },

  content: {
    flex: 1,
    flexDirection: "row",
  },

  graphArea: {
    flex: 1,
    minHeight: GRAPH_HEIGHT,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#F8FAFC",
  },

  detailsPanel: {
    width: 300,
    padding: 24,
    borderLeftWidth: 1,
    borderLeftColor: "#E5E7EB",
    backgroundColor: "#FFFFFF",
  },

  detailsHeading: {
    color: "#111827",
    fontSize: 18,
    fontWeight: "800",
    marginBottom: 18,
  },

  entityBadge: {
    alignSelf: "flex-start",
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    marginBottom: 24,
  },

  entityBadgeText: {
    color: "#FFFFFF",
    fontSize: 12,
    fontWeight: "700",
  },

  basicInfo: {
    marginBottom: 18,
  },

  infoLabel: {
    fontSize: 11,
    color: "#9CA3AF",
    fontWeight: "700",
    textTransform: "uppercase",
  },

  infoValue: {
    color: "#111827",
    fontSize: 14,
    fontWeight: "600",
    marginTop: 5,
  },

  divider: {
    height: 1,
    backgroundColor: "#E5E7EB",
    marginVertical: 10,
  },

  propertiesTitle: {
    color: "#111827",
    fontWeight: "800",
    fontSize: 14,
    marginVertical: 16,
  },

  propertyRow: {
    flexDirection: "row",
    justifyContent: "space-between",
    gap: 15,
    marginBottom: 14,
  },

  propertyKey: {
    color: "#6B7280",
    fontSize: 12,
  },

  propertyValue: {
    color: "#111827",
    fontSize: 12,
    fontWeight: "600",
    textAlign: "right",
  },

  emptyDetails: {
    flex: 1,
    alignItems: "center",
    justifyContent: "center",
  },

  emptyIcon: {
    fontSize: 45,
    color: "#CBD5E1",
  },

  emptyTitle: {
    color: "#111827",
    fontSize: 16,
    fontWeight: "700",
    marginTop: 14,
  },

  emptyDescription: {
    color: "#9CA3AF",
    textAlign: "center",
    fontSize: 12,
    lineHeight: 18,
    marginTop: 7,
  },
});