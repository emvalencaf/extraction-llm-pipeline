# Lambda container image (AWS base image ships the Runtime Interface Emulator).
# The handler is chosen per service via `command` in compose.yaml.
FROM public.ecr.aws/lambda/python:3.12

RUN pip install --no-cache-dir "pydantic>=2.14" "pypdf>=6.21" "langgraph>=1.0" \
    "presidio-analyzer>=2.2.366"
COPY src/invoice_extraction ${LAMBDA_TASK_ROOT}/invoice_extraction

CMD ["invoice_extraction.entrypoints.api_handler.handler"]
