import { vs2015 } from "react-syntax-highlighter/dist/esm/styles/hljs";
import { github } from "react-syntax-highlighter/dist/esm/styles/hljs";
import { useTheme } from "@/hooks/use-theme";

export function useSyntaxTheme() {
  const { theme } = useTheme();
  return theme === "dark" ? vs2015 : github;
}
