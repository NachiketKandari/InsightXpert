"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type Node,
  type Edge,
  applyNodeChanges,
  applyEdgeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useAutomationStore } from "@/stores/automation-store";
import { SQLBlockNode } from "./sql-block-node";
import type { WorkflowBlock, WorkflowEdge } from "@/types/automation";

const nodeTypes = { sqlBlock: SQLBlockNode };

function blocksToNodes(blocks: WorkflowBlock[]): Node[] {
  return blocks.map((b) => ({
    id: b.id,
    type: "sqlBlock",
    position: b.position,
    data: { ...b, type: "sqlBlock" },
  }));
}

function edgesToRFEdges(edges: WorkflowEdge[]): Edge[] {
  return edges.map((e) => ({
    id: e.id,
    source: e.sourceBlockId,
    target: e.targetBlockId,
    animated: true,
    style: { stroke: "hsl(var(--primary))", strokeWidth: 2 },
  }));
}

export function WorkflowCanvas() {
  const blocks = useAutomationStore((s) => s.workflowBlocks);
  const edges = useAutomationStore((s) => s.workflowEdges);
  const updateBlockPosition = useAutomationStore((s) => s.updateBlockPosition);
  const addEdge = useAutomationStore((s) => s.addEdge);
  const removeEdge = useAutomationStore((s) => s.removeEdge);

  const nodes = useMemo(() => blocksToNodes(blocks), [blocks]);
  const rfEdges = useMemo(() => edgesToRFEdges(edges), [edges]);

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // Apply changes for position updates
      const updated = applyNodeChanges(changes, nodes);
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          updateBlockPosition(change.id, change.position);
        }
      }
      // We let React re-derive nodes from store on next render
      void updated;
    },
    [nodes, updateBlockPosition],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const change of changes) {
        if (change.type === "remove") {
          removeEdge(change.id);
        }
      }
      void applyEdgeChanges(changes, rfEdges);
    },
    [rfEdges, removeEdge],
  );

  const handleConnect = useCallback(
    (connection: Connection) => {
      if (!connection.source || !connection.target) return;
      // Prevent duplicate edges
      const exists = edges.some(
        (e) =>
          e.sourceBlockId === connection.source &&
          e.targetBlockId === connection.target,
      );
      if (exists) return;
      addEdge({
        id: `edge-${connection.source}-${connection.target}`,
        sourceBlockId: connection.source,
        targetBlockId: connection.target,
      });
    },
    [edges, addEdge],
  );

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        fitView
        snapToGrid
        snapGrid={[16, 16]}
        proOptions={{ hideAttribution: true }}
        className="bg-background"
      >
        <Background gap={16} size={1} />
        <Controls className="!bg-card !border-border !shadow-sm [&>button]:!bg-card [&>button]:!border-border [&>button]:!fill-foreground" />
        <MiniMap
          className="!bg-card !border-border"
          nodeColor="hsl(var(--primary))"
          maskColor="hsl(var(--background) / 0.8)"
        />
      </ReactFlow>
    </div>
  );
}
