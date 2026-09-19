import OpenAI from "openai";

let client: OpenAI | null = null;
let attempted = false;

export function isAiConfigured(): boolean {
  return !!process.env.OPENAI_API_KEY;
}

export function getOpenAiClient(): OpenAI | null {
  if (!isAiConfigured()) return null;
  if (!attempted) {
    attempted = true;
    client = new OpenAI({ apiKey: process.env.OPENAI_API_KEY });
  }
  return client;
}

export function getConfiguredModel(businessModel: string | undefined): string {
  return process.env.OPENAI_MODEL || businessModel || "gpt-4.1-mini";
}
