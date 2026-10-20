# Model artifacts removed

The active backend is a scraping-only service. It does not load or require
IndoBERT, PyTorch, Transformers, tokenizer files, or model checkpoints.

The directory is retained only to avoid breaking external volume mounts from
older deployments.
