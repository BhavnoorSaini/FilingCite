"""Download the embedding model's files into EMBEDDING_MODEL_DIR so they ship with the backend.

Usage (from backend/):  uv run --env-file ../.env python -m scripts.download_model
"""

import os

from fastembed import TextEmbedding
from huggingface_hub import snapshot_download

from embedding import model_dir


def main() -> None:
    name = os.environ["EMBEDDING_MODEL"]
    info = next(m for m in TextEmbedding.list_supported_models() if m["model"] == name)
    target = model_dir()
    snapshot_download(
        repo_id=info["sources"]["hf"],
        local_dir=target,
        allow_patterns=[
            info["model_file"],
            "config.json",
            "tokenizer*.json",
            "special_tokens_map.json",
        ],
    )
    print(f"Saved {name} to {target}")


if __name__ == "__main__":
    main()
