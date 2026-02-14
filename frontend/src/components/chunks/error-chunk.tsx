"use client";

import { AlertCircle } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";

interface ErrorChunkProps {
  content: string;
}

export function ErrorChunk({ content }: ErrorChunkProps) {
  return (
    <Card className="border-destructive/50 bg-destructive/10">
      <CardContent className="flex items-start gap-3 py-3">
        <AlertCircle className="h-4 w-4 text-destructive shrink-0 mt-0.5" />
        <p className="text-sm text-destructive">{content}</p>
      </CardContent>
    </Card>
  );
}
