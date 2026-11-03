import os
from functools import cache
from pathlib import Path

from fastembed import TextEmbedding

BACKEND_DIR = Path(__file__).resolve().parent


def model_dir() -> Path:
    """Folder holding the bundled model files (relative paths resolve from backend/)."""
    return BACKEND_DIR / os.environ["EMBEDDING_MODEL_DIR"]


@cache
def _model() -> TextEmbedding:
    # Load only from the bundled folder; never download at runtime.
    return TextEmbedding(
        model_name=os.environ["EMBEDDING_MODEL"],
        specific_model_path=str(model_dir()),
        local_files_only=True,
    )


def embed_passages(texts: list[str]) -> list:
    # Small batches avoid padding every text to the longest one in the batch.
    batch_size = int(os.environ["EMBEDDING_BATCH_SIZE"])
    return list(_model().passage_embed(texts, batch_size=batch_size))


def embed_query(text: str):
    return next(_model().query_embed(text))
