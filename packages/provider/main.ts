import { createProviderRegistry, generateText} from 'ai';
import { openai } from '@ai-sdk/openai';
import { anthropic } from '@ai-sdk/anthropic';
import { google } from '@ai-sdk/google';

google("gemini-2.0-flash");
export const registry = createProviderRegistry({
  // register provider with prefix and direct provider import:
  anthropic,
  openai,
});

const { text } = await generateText({
  model: registry.languageModel('openai:gpt-5.1'), // default separator
  // or with custom separator:
  // model: customSeparatorRegistry.languageModel('openai > gpt-5.1'),
  prompt: 'Invent a new holiday and describe its traditions.',
});