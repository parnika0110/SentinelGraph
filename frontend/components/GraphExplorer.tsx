"use client";

import { useMemo } from "react";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { Badge, LABEL_STYLES, LoadingState, ErrorState, EmptyState } from "@/components/ui";
import type { NeighborhoodResponse } from "@/lib/api";

// ---------------------------------------------------------------------------
// Custom entity node: label chip + id, colored by graph label.
// ---------------------------------------------------------------------------

export interface EntityNodeData extends Record<string, unknown> {
  entityLabel: string;
  entityId: string;
  subtitle: string;
  isCenter: boolean;
}

function EntityNode({ data }: NodeProps<Node<EntityNodeData>>) {
  const style = LABEL_STYLES[data.entityLabel] ?? "bg-slate-500/15 text-slate-300 border-slate-500/40";
  return (
    <div
      className={`rounded-sm border px-2.5 py-1.5 text-left ${
        style
      } ${data.isCenter ? "ring-2 ring-sky-400/80" : ""} min-w-[130px] max-w-[190px] bg-slate-950/80 backdrop-blur`}
      title={`${data.entityLabel}: ${data.entityId}`}
    >
      <Handle type="target" position={Position.Left} className="!bg-slate-500" />
      <p className="text-[9px] font-semibold uppercase tracking-wider opacity-70">
        {data.entityLabel}
      </p>
      <p className="truncate font-mono text-[11px] font-medium">{data.entityId}</p>
      {data.subtitle && (
        <p className="truncate text-[9px] opacity-60">{data.subtitle}</p>
      )}
      <Handle type="source" position={Position.Right} className="!bg-slate-500" />
    </div>
  );
}

const nodeTypes = { entity: EntityNode };

// ---------------------------------------------------------------------------
// Layout: BFS layers from the center node -> left-to-right columns.
// ---------------------------------------------------------------------------

const ACTIVITY_RELS = new Set(["LOGGED_IN_FROM", "RUNS", "CONNECTS_TO", "INVOLVES", "OBSERVED_ON"]);

function layout(nb: NeighborhoodResponse) {
  const byId = new Map(nb.nodes.map((n) => [n.id, n]));
  const adjacency = new Map<string, string[]>();
  for (const e of nb.edges) {
    if (!adjacency.has(e.src)) adjacency.set(e.src, []);
    if (!adjacency.has(e.dst)) adjacency.set(e.dst, []);
    adjacency.get(e.src)!.push(e.dst);
    adjacency.get(e.dst)!.push(e.src);
  }

  const depth = new Map<string, number>([[nb.center_id, 0]]);
  const queue = [nb.center_id];
  while (queue.length) {
    const cur = queue.shift()!;
    for (const nxt of adjacency.get(cur) ?? []) {
      if (!depth.has(nxt)) {
        depth.set(nxt, depth.get(cur)! + 1);
        queue.push(nxt);
      }
    }
  }

  const columns = new Map<number, string[]>();
  for (const n of nb.nodes) {
    const d = depth.get(n.id) ?? 1;
    if (!columns.has(d)) columns.set(d, []);
    columns.get(d)!.push(n.id);
  }

  const COL_WIDTH = 240;
  const ROW_HEIGHT = 92;
  const positions: Record<string, { x: number; y: number }> = {};
  const sortedDepths = [...columns.keys()].sort((a, b) => a - b);
  for (const d of sortedDepths) {
    const ids = columns.get(d)!;
    ids.forEach((id, i) => {
      positions[id] = {
        x: d * COL_WIDTH + 40,
        y: i * ROW_HEIGHT + 40,
      };
    });
  }

  const flowNodes: Node<EntityNodeData>[] = nb.nodes.map((n) => {
    const node = byId.get(n.id)!;
    const p = positions[n.id] ?? { x: 0, y: 0 };
    const subtitle =
      (node.props.title as string) ??
      (node.props.hostname as string) ??
      (node.props.address as string) ??
      (node.props.account_name as string) ??
      (node.props.name as string) ??
      "";
    return {
      id: n.id,
      type: "entity",
      position: p,
      data: {
        entityLabel: n.label,
        entityId: n.id,
        subtitle: String(subtitle).slice(0, 60),
        isCenter: n.id === nb.center_id,
      },
    };
  });

  const flowEdges: Edge[] = nb.edges.map((e) => {
    const activity = ACTIVITY_RELS.has(e.type) && e.type !== "INVOLVES";
    const ts = (e.props.ts as string) ?? "";
    return {
      id: e.id,
      source: e.src,
      target: e.dst,
      label: ts ? `${e.type} · ${ts.slice(11, 16)}` : e.type,
      animated: activity,
      labelBgStyle: { fill: "#181a17" },
      labelStyle: { fill: "#9a9c91", fontSize: 9 },
      style: { stroke: activity ? "#c5f36b" : "#5a5c54", strokeDasharray: activity ? undefined : "4 3" },
      markerEnd: { type: MarkerType.ArrowClosed, width: 12, height: 12, color: activity ? "#c5f36b" : "#5a5c54" },
    };
  });

  return { flowNodes, flowEdges };
}

// ---------------------------------------------------------------------------

export default function GraphExplorer({
  data,
  loading,
  error,
  onNodeClick,
}: {
  data: NeighborhoodResponse | null;
  loading: boolean;
  error: string | null;
  onNodeClick?: (nodeId: string) => void;
}) {
  const { flowNodes, flowEdges } = useMemo(
    () => (data ? layout(data) : { flowNodes: [], flowEdges: [] }),
    [data],
  );

  if (error) return <ErrorState message={error} />;
  if (loading) return <LoadingState label="Querying FalkorDB" />;
  if (!data || data.nodes.length === 0)
    return (
      <EmptyState
        title="No graph neighborhood"
        hint="Select an alert from the queue to traverse its relationships in FalkorDB."
      />
    );

  const activityCount = flowEdges.filter((e) => e.animated).length;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-2 flex flex-wrap items-center gap-1.5">
        <Badge className="border-sky-500/40 bg-sky-500/10 text-sky-300">
          {data.nodes.length} nodes
        </Badge>
        <Badge className="border-slate-500/40 bg-slate-500/10 text-slate-400">
          {data.edges.length} rels
        </Badge>
        <Badge className="border-cyan-500/40 bg-cyan-500/10 text-cyan-300">
          {activityCount} activity
        </Badge>
        <span className="text-[10px] text-slate-500">
          solid blue = observed activity · dashed = inventory
        </span>
      </div>
      <div className="h-full min-h-[340px] flex-1 rounded-sm border border-white/10 bg-slate-950/60">
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.2}
          maxZoom={2}
          nodesDraggable
          nodesConnectable={false}
          elementsSelectable
          onNodeClick={(_, node) => onNodeClick?.(node.id)}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={18} color="#30332d" />
          <Controls showInteractive={false} />
          <MiniMap
            pannable
            zoomable
            nodeColor={(n) => {
              const l = (n.data as EntityNodeData).entityLabel;
              return l === "Alert"
                ? "#e0674f"
                : l === "Device"
                  ? "#b0a285"
                  : l === "Account"
                    ? "#c5f36b"
                    : l === "IPAddress"
                      ? "#d9a441"
                      : "#7a7c72";
            }}
            maskColor="rgba(2,6,23,0.7)"
          />
        </ReactFlow>
      </div>
    </div>
  );
}
