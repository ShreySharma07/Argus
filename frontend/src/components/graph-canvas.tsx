import { Text, View } from "react-native";

import type { GraphData } from "../lib/api";

/** Native fallback: the glowing canvas is web-only (DOM SVG filters). */
export default function GraphCanvas({ data, height = 620 }: {
  data: GraphData; height?: number; focusId?: string; onOpenCase?: (caseId: string) => void;
}) {
  return (
    <View style={{ height, backgroundColor: "#05070C", borderRadius: 10, alignItems: "center", justifyContent: "center" }}>
      <Text style={{ color: "#8491A6", fontSize: 12 }}>
        {data.nodes.length} entities · {data.edges.length} relationships — open on web for the interactive graph
      </Text>
    </View>
  );
}
