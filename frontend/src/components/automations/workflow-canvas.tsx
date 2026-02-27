"use client";

import { useCallback, useMemo } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MarkerType,
  ConnectionLineType,
  type Connection,
  type NodeChange,
  type EdgeChange,
  type Node,
  type Edge,
  applyNodeChanges,
  applyEdgeChanges,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Workflow, Link2, Sparkles } from "lucide-react";
import { useAutomationStore } from "@/stores/automation-store";
import { SQLBlockNode } from "./sql-block-node";
import type { WorkflowBlock, WorkflowEdge } from "@/types/automation";
import { Button } from "@/components/ui/button";

const nodeTypes = { sqlBlock: SQLBlockNode };

// Visible, prominent edge style
const EDGE_COLOR = "oklch(0.65 0.15 230)";
const EDGE_COLOR_MUTED = "oklch(0.55 0.05 230)";

const defaultEdgeOptions = {
  type: "default" as const,
  animated: true,
  markerEnd: {
    type: MarkerType.ArrowClosed,
    color: EDGE_COLOR,
    width: 20,
    height: 20,
  },
  style: {
    stroke: EDGE_COLOR,
    strokeWidth: 2.5,
  },
};

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
    type: "default",
    animated: true,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: EDGE_COLOR,
      width: 20,
      height: 20,
    },
    style: {
      stroke: EDGE_COLOR,
      strokeWidth: 2.5,
    },
    label: "",
  }));
}

function suggestedToRFEdges(suggested: WorkflowEdge[]): Edge[] {
  return suggested.map((e) => ({
    id: e.id,
    source: e.sourceBlockId,
    target: e.targetBlockId,
    type: "default",
    animated: false,
    markerEnd: {
      type: MarkerType.ArrowClosed,
      color: EDGE_COLOR_MUTED,
      width: 16,
      height: 16,
    },
    style: {
      stroke: EDGE_COLOR_MUTED,
      strokeWidth: 1.5,
      strokeDasharray: "8 5",
      opacity: 0.5,
    },
    selectable: false,
    deletable: false,
  }));
}

export function WorkflowCanvas() {
  const blocks = useAutomationStore((s) => s.workflowBlocks);
  const edges = useAutomationStore((s) => s.workflowEdges);
  const updateBlockPosition = useAutomationStore((s) => s.updateBlockPosition);
  const addEdge = useAutomationStore((s) => s.addEdge);
  const removeEdge = useAutomationStore((s) => s.removeEdge);
  const getSuggestedEdges = useAutomationStore((s) => s.getSuggestedEdges);
  const applySuggestedEdges = useAutomationStore((s) => s.applySuggestedEdges);

  const suggestedEdges = getSuggestedEdges();

  const nodes = useMemo(() => blocksToNodes(blocks), [blocks]);
  const rfEdges = useMemo(
    () => [...edgesToRFEdges(edges), ...suggestedToRFEdges(suggestedEdges)],
    [edges, suggestedEdges],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      const updated = applyNodeChanges(changes, nodes);
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          updateBlockPosition(change.id, change.position);
        }
      }
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

  const hasBlocks = blocks.length > 0;
  const showConnectHint = blocks.length >= 2 && edges.length === 0;

  return (
    <div className="h-full w-full relative">
      <ReactFlow
        nodes={nodes}
        edges={rfEdges}
        nodeTypes={nodeTypes}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onConnect={handleConnect}
        defaultEdgeOptions={defaultEdgeOptions}
        connectionLineType={ConnectionLineType.Bezier}
        connectionLineStyle={{
          stroke: EDGE_COLOR,
          strokeWidth: 2.5,
          strokeDasharray: "6 3",
        }}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        snapToGrid
        snapGrid={[16, 16]}
        proOptions={{ hideAttribution: true }}
        className="bg-background"
        deleteKeyCode="Delete"
      >
        <Background gap={20} size={1} className="opacity-30" />
        <Controls className="!bg-card !border-border !shadow-sm [&>button]:!bg-card [&>button]:!border-border [&>button]:!fill-foreground" />
      </ReactFlow>

      {/* Empty state */}
      {!hasBlocks && (
        <div className="absolute inset-0 flex items-center justify-center pointer-events-none z-10">
          <div className="text-center space-y-3 max-w-[260px]">
            <div className="mx-auto size-14 rounded-xl bg-muted/50 border border-border flex items-center justify-center">
              <Workflow className="size-6 text-muted-foreground/50" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-medium text-muted-foreground">
                No blocks yet
              </p>
              <p className="text-xs text-muted-foreground/60 leading-relaxed">
                Add SQL blocks from the sidebar to start building your workflow
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Connect-blocks hint (2+ blocks, no edges) */}
      {showConnectHint && (
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center gap-2">
          {suggestedEdges.length > 0 && (
            <Button
              size="sm"
              variant="outline"
              className="shadow-md backdrop-blur-sm bg-card/95 border-primary/30 hover:border-primary"
              onClick={applySuggestedEdges}
            >
              <Sparkles className="size-3.5 mr-1.5 text-primary" />
              Auto-connect ({suggestedEdges.length} suggestion{suggestedEdges.length !== 1 ? "s" : ""})
            </Button>
          )}
          <div className="bg-card/95 border border-primary/30 rounded-lg px-3.5 py-2 shadow-md backdrop-blur-sm flex items-center gap-2 pointer-events-none">
            <Link2 className="size-3.5 text-primary flex-shrink-0" />
            <span className="text-xs text-muted-foreground">
              Drag from a block&apos;s{" "}
              <span className="text-foreground font-medium">bottom handle</span>{" "}
              to connect blocks in sequence
            </span>
          </div>
        </div>
      )}

      {/* Auto-connect button when there are edges but also suggestions */}
      {!showConnectHint && suggestedEdges.length > 0 && (
        <div className="absolute bottom-20 left-1/2 -translate-x-1/2 z-10">
          <Button
            size="sm"
            variant="outline"
            className="shadow-md backdrop-blur-sm bg-card/95 border-primary/30 hover:border-primary"
            onClick={applySuggestedEdges}
          >
            <Sparkles className="size-3.5 mr-1.5 text-primary" />
            Auto-connect ({suggestedEdges.length} suggestion{suggestedEdges.length !== 1 ? "s" : ""})
          </Button>
        </div>
      )}
    </div>
  );
}
