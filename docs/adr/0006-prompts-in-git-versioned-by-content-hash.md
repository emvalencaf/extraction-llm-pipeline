# Prompts live in git, versioned by content hash

The Prompt Bundle (system prompt, few-shot examples, repair prompt, per-model
settings) is a set of files packaged into the image. Its version is the first 12
characters of the SHA-256 of its canonical contents, checked against a manifest at
cold start; a missing or corrupt bundle fails fast as an infrastructure failure.
Merging to `master` and deploying is the promotion, and `git revert` is the
rollback. SSM (4 KB cap), AppConfig, LangSmith Prompt Hub and Bedrock Prompt
Management were rejected: they add a runtime dependency and a second source of
truth for something the regression gate already protects in the PR.

Few-shot examples are static and come from the Train Set only, which a CI check
enforces.
