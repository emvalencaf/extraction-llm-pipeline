# One `prod` environment, no staging

There is a single `prod` environment: no dev, staging or ephemeral stack. The
regression gate needs no deployed target because it runs in-process, and a
post-deploy smoke test covers the deployed path. Merging to `development` never
deploys. This is deliberate scoping for a free-tier portfolio project, so the
cost guardrail is a tag-filtered budget alarm instead of environment isolation.
