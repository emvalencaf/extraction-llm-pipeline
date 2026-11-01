# 60/20/20 split where the Test Set is never used for tuning

The 100 Kaggle invoices are split 60 train, 20 validation and 20 test, seeded and
stratified by item count, and committed as a Split Manifest. Train supplies
few-shot examples, validation tunes prompts and models, and the test split feeds
the CI regression gate only. The earlier name "golden set" was dropped so nobody
tunes against the gate's data.
