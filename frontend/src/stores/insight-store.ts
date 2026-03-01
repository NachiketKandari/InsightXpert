import { create } from "zustand";
import { apiCall } from "@/lib/api";
import type { Insight } from "@/types/insight";

interface InsightState {
  insights: Insight[];
  allInsights: Insight[];
  totalCount: number;
  isLoading: boolean;
  isLoadingAll: boolean;

  fetchInsights: (bookmarked?: boolean) => Promise<void>;
  fetchAllInsights: () => Promise<void>;
  fetchCount: () => Promise<void>;
  bookmarkInsight: (id: string, bookmarked: boolean) => Promise<void>;
  deleteInsight: (id: string) => Promise<void>;
}

interface InsightsResponse {
  insights: Insight[];
  total: number;
}

const _fetchSlice = async (
  url: string,
  stateKey: "insights" | "allInsights",
  loadingKey: "isLoading" | "isLoadingAll",
  bookmarked: boolean,
  set: (partial: Partial<InsightState>) => void,
) => {
  set({ [loadingKey]: true });
  try {
    const params = bookmarked ? "?bookmarked=true" : "";
    const data = await apiCall<InsightsResponse>(`${url}${params}`);
    set({ [stateKey]: data?.insights ?? [], [loadingKey]: false });
  } catch {
    set({ [loadingKey]: false });
  }
};

export const useInsightStore = create<InsightState>((set, get) => ({
  insights: [],
  allInsights: [],
  totalCount: 0,
  isLoading: false,
  isLoadingAll: false,

  fetchInsights: async (bookmarked = false) => {
    await _fetchSlice("/api/insights", "insights", "isLoading", bookmarked, set);
  },

  fetchAllInsights: async () => {
    await _fetchSlice("/api/insights/all", "allInsights", "isLoadingAll", false, set);
  },

  fetchCount: async () => {
    const data = await apiCall<{ count: number }>("/api/insights/count");
    if (data) set({ totalCount: data.count });
  },

  bookmarkInsight: async (id, bookmarked) => {
    // Optimistic update
    const prev = get();
    const update = (list: Insight[]) =>
      list.map((i) => (i.id === id ? { ...i, is_bookmarked: bookmarked } : i));
    set({
      insights: update(prev.insights),
      allInsights: update(prev.allInsights),
    });
    apiCall<{ status: string }>(`/api/insights/${id}/bookmark`, {
      method: "PATCH",
      body: JSON.stringify({ bookmarked }),
    }).catch(() => {
      set({ insights: prev.insights, allInsights: prev.allInsights });
    });
  },

  deleteInsight: async (id) => {
    // Optimistic update
    const prev = get();
    set({
      insights: prev.insights.filter((i) => i.id !== id),
      allInsights: prev.allInsights.filter((i) => i.id !== id),
      totalCount: Math.max(0, prev.totalCount - 1),
    });
    apiCall<{ status: string }>(`/api/insights/${id}`, {
      method: "DELETE",
    }).catch(() => {
      set({
        insights: prev.insights,
        allInsights: prev.allInsights,
        totalCount: prev.totalCount,
      });
    });
  },
}));
