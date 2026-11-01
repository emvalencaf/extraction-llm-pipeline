# Decisions

* [Hexagonal package, shipped as container images](0001-hexagonal-package-and-container-images.md) - All code lives in one package, `src/invoice_extraction/`, split into `domain/`, `application/`, `adapters/`, `compositio
* [Text-first input, staged in S3 zones](0002-text-first-input-in-s3-zones.md) - The model receives the text layer of the PDF, never the native PDF
* [Reversible anonymization with Presidio and our own Placeholder map](0003-reversible-anonymization-with-presidio.md) - Seller and client identity, tax ids, contacts and bank details are replaced by `[TYPE_n]` placeholders before the model 
* [Business failures are terminal; the DLQ is for infrastructure only](0004-business-failures-are-terminal-dlq-is-for-infrastructure.md) - When validation still fails after repair and escalation, or the PDF has no text layer, the job ends as `failed_validatio
* [Presigned S3 upload, with S3 events going straight to SQS](0005-presigned-upload-and-s3-events-straight-to-sqs.md) - `POST /jobs` returns a presigned PUT URL and the client uploads the PDF to `raw/{job_id}.pdf`, so the 10 MB and 29 s API
* [Prompts live in git, versioned by content hash](0006-prompts-in-git-versioned-by-content-hash.md) - The Prompt Bundle (system prompt, few-shot examples, repair prompt, per-model settings) is a set of files packaged into 
* [60/20/20 split where the Test Set is never used for tuning](0007-train-validation-test-split-with-untouchable-test-set.md) - The 100 Kaggle invoices are split 60 train, 20 validation and 20 test, seeded and stratified by item count, and committe
* [Deterministic regression gate with a committed baseline](0008-deterministic-regression-gate-with-committed-baseline.md) - The gate runs the real graph in-process in CI on the Test Set, scoring with assayer's deterministic per-field metrics ag
* [One `prod` environment, no staging](0009-single-prod-environment.md) - There is a single `prod` environment: no dev, staging or ephemeral stack
* [Terraform state, bootstrap and full teardown](0010-terraform-state-bootstrap-and-teardown.md) - `infra/bootstrap/` (local state, run once by hand) creates the state bucket and this repository's CI roles; everything e
* [Native API Gateway key, 403 on a bad key, single-tenant access](0011-native-api-gateway-key-and-single-tenant-access.md) - The API is a REST API (HTTP APIs have no API keys) with a native key on a usage plan, so API Gateway rejects bad calls b
* [Local stack from per-service emulators, with a fake Gemini](0012-local-stack-emulators-and-fake-gemini.md) - The local stack uses the Lambda RIE with the real image, DynamoDB Local, a moto S3 server and ElasticMQ for the queues, 
* [Wide events with embedded metrics; no LangSmith](0013-wide-events-and-emf-without-langsmith.md) - Observability is two JSON wide events joined by `job_id` (`llm_call` and `job`), with CloudWatch metrics embedded as EMF
* [Deploy from `master` behind approval; rollback is a revert](0014-deploy-from-master-with-approval-and-no-auto-rollback.md) - `deploy.yml` runs on push to `master`: gate (only if extraction paths changed since the last successful deployment), `te
* [Secrets in SSM Standard SecureString](0015-secrets-in-ssm-standard-securestring.md) - The production Gemini key and the API key live in SSM SecureString parameters of the Standard tier, encrypted with the A
