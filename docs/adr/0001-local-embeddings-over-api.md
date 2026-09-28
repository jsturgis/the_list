# Local embedding model over API-hosted embeddings

We use a local open-source embedding model (Qwen3-Embedding-8B or similar) served via Ollama rather than an API provider such as OpenAI text-embedding or Anthropic. The constraint is that the system must run on a MacBook Pro or low-power cloud infrastructure without per-call API cost. Changing the embedding model later requires re-embedding every Band and Show record, so this choice is load-bearing from day one.

## Considered Options

- **OpenAI text-embedding-3-small / ada-002**: easiest integration, strong quality, but incurs per-call cost and introduces an external dependency for a write-path operation that runs on every ingest.
- **Ollama + Qwen3-Embedding-8B**: zero marginal cost, runs on Apple Silicon (M-series), consistent behaviour between local dev and cloud. Chosen.
- **nomic-embed-text (137M via Ollama)**: lighter fallback if 8B proves too heavy for the target cloud VM; same Ollama runtime, swap is a one-line config change.
