import { cn } from "@/lib/utils";

interface ListLoadingProps {
  spinnerClassName?: string;
}

export function ListLoading({ spinnerClassName }: ListLoadingProps) {
  return (
    <div className="flex items-center justify-center py-12">
      <div className={cn("animate-spin rounded-full h-8 w-8 border-b-2", spinnerClassName ?? "border-primary")} />
    </div>
  );
}

interface ListEmptyStateProps {
  icon: React.ReactNode;
  message: string;
}

export function ListEmptyState({ icon, message }: ListEmptyStateProps) {
  return (
    <div className="text-center py-12">
      {icon}
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}
