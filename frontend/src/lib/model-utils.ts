export const PROVIDER_LABELS: Record<string, string> = {
  gemini: "Gemini",
  ollama: "Ollama",
};

/** Check if the model belongs to the provider (e.g. "gemini-2.5-flash" is gemini, "gemma-3-27b-it" is not) */
export function isProviderModel(model: string, provider: string): boolean {
  const lower = model.toLowerCase();
  return lower.startsWith(provider + "-") || lower.startsWith(provider + "/");
}

/** Strip provider prefix and title-case: "gemini-2.5-flash" -> "2.5 Flash" */
export function formatModelName(model: string, provider: string): string {
  let name = model;
  // Strip provider prefix (e.g. "gemini-", "ollama/")
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
