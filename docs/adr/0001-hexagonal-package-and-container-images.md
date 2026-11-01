# Hexagonal package, shipped as container images

All code lives in one package, `src/invoice_extraction/`, split into `domain/`,
`application/`, `adapters/`, `composition/` and `entrypoints/`, with imports
pointing inward only and enforced by import-linter. LangGraph and boto3 stay out
of `domain/`, so the pipeline is tested through its ports with fakes instead of
mocks. Presidio plus spaCy exceed the Lambda zip limit, so both functions ship
as one shared container image, with the handler chosen per function.

## Consequences

Every new infrastructure dependency needs a port first. Zip packaging is no
longer an option without dropping Presidio.
