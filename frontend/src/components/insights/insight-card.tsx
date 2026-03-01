import { Bookmark } from "lucide-react";
import type { Insight } from "@/types/insight";
import { CATEGORY_COLOR, DEFAULT_CATEGORY_COLOR } from "./constants";

interface InsightCardProps {
  insight: Insight;
  onClick: (i: Insight) => void;
  onBookmark?: (id: string, bookmarked: boolean) => void;
  showUserEmail?: boolean;
  isSelected?: boolean;
}

export function InsightCard({
  insight: i,
  onClick,
  onBookmark,
  showUserEmail,
  isSelected,
}: InsightCardProps) {
  return (
    <div
      className={`group flex items-start gap-3 rounded-md border p-3 cursor-pointer transition-colors hover:bg-muted/50 ${
        isSelected
          ? "border-amber-500/40 bg-amber-500/10"
          : "border-border/50"
      }`}
      onClick={() => onClick(i)}
    >
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium truncate">{i.title}</p>
        <p className="text-xs text-muted-foreground truncate mt-0.5">
          {i.summary}
        </p>
        <div className="flex items-center gap-1.5 mt-1.5 flex-wrap">
          {i.categories.map((cat) => (
            <span
              key={cat}
              className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium ${CATEGORY_COLOR[cat] ?? DEFAULT_CATEGORY_COLOR}`}
            >
              {cat.replace(/_/g, " ")}
            </span>
          ))}
        </div>
        <div className="flex items-center gap-2 mt-1 text-xs text-muted-foreground flex-wrap">
          {showUserEmail && i.user_email && (
            <span className="font-medium text-foreground/70">
              {i.user_email}
            </span>
          )}
          <span>{new Date(i.created_at).toLocaleString()}</span>
        </div>
      </div>
      {onBookmark && (
        <button
          type="button"
          className={`p-1.5 rounded-md transition-all shrink-0 mt-0.5 ${
            i.is_bookmarked
              ? "text-amber-500"
              : "opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-amber-500"
          } hover:bg-amber-500/10`}
          onClick={(e) => {
            e.stopPropagation();
            onBookmark(i.id, !i.is_bookmarked);
          }}
          title={i.is_bookmarked ? "Remove bookmark" : "Bookmark"}
        >
          <Bookmark className={`size-4 ${i.is_bookmarked ? "fill-current" : ""}`} />
        </button>
      )}
    </div>
  );
}
