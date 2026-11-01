# Deploy from `master` behind approval; rollback is a revert

`deploy.yml` runs on push to `master`: gate (only if extraction paths changed since
the last successful deployment), `terraform plan`, approval on the `production`
Environment, apply of the approved plan, then a smoke test. Images are tagged with
the commit SHA, never `latest`. There is no automatic rollback, because a
half-reverted apply is worse; the normal path is `git revert`, and the emergency
path is a `workflow_dispatch` by SHA that skips the gate but still needs approval.
GitHub authenticates to AWS through OIDC with a read-only `plan` role and a
`deploy` role assumable only by the job on the `production` Environment.

The repository is public: a private one on the Free plan has neither branch
protection nor required reviewers, and only 2,000 Actions minutes a month.
