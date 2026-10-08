# Hardware profiles

A profile sets which compose files and optional services run, and which model preset
is the default. Switch with:

    make profile P=cpu        # or t4x2, t4-split

| Profile | Hardware | Default model | Docling OCR | Embeddings |
|---|---|---|---|---|
| `t4x2` | 2× Tesla T4 | Qwen3.6-35B-A3B split over both GPUs | on | Qwen3-Embedding-0.6B |
| `t4-split` | 2× Tesla T4 | Qwen3.6-35B-A3B on GPU 0 (+ RAM) | on | Qwen3-Embedding-0.6B |
| `cpu` | any x86-64 PC, 8 GB+ RAM | Qwen3.5-2B (or 4B) on CPU | off | all-MiniLM-L6-v2 |

All tools behave the same in every profile; only speed and quality change.
Without Docling, scanned PDFs can't be OCR'd and documents use simpler extraction.
