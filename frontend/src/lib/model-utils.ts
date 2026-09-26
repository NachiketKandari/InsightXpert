export const PROVIDER_LABELS: Record<string, string> = {
  deepseek: "DeepSeek",
  openrouter: "OpenRouter",
  ollama: "Ollama",
};

/** Strip provider prefix and title-case: "deepseek-v4-flash" -> "V4 Flash" */
export function formatModelName(model: string, provider: string): string {
  let name = model;
  // Strip provider prefix (e.g. "deepseek-", "openrouter/")
  const prefixes = [provider + "-", provider + "/"];
  for (const p of prefixes) {
    if (name.toLowerCase().startsWith(p)) {
      name = name.slice(p.length);
      break;
    }
  }
  // Replace hyphens/underscores with spaces and title-case each word
  return name
    .replace(/[-_]/g, " ")
    .replace(/\b[a-z]/g, (c) => c.toUpperCase());
}
