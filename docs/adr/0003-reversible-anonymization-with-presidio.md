# Reversible anonymization with Presidio and our own Placeholder map

Seller and client identity, tax ids, contacts and bank details are replaced by
`[TYPE_n]` placeholders before the model call and restored by exact string
substitution afterwards. The Gemini free tier may train on prompts, which is the
real motive. Detection uses Presidio with hand-added Indian recognizers; the
placeholder map lives only in graph state, is rebuilt on redelivery and is never
persisted or logged. A missing, altered or leftover placeholder is a validation
failure that feeds the repair loop, with no fuzzy matching.

## Considered options

LLM Guard (archived), Guardrails AI (heavy wrapper over Presidio), NeMo
Guardrails (chat runtime) and LangChain `PIIMiddleware` (no NER, reversibility
not stated) were rejected. Guardrails are our own small nodes, and prompt
injection is covered by delimiting the text as untrusted data and accepting only
the schema-fixed tool call, not by a classifier.
