import os
from functools import cache
from pathlib import Path

from fastembed import TextEmbedding

BACKEND_DIR = Path(__file__).resolve().parent


@cache
def _model() -> TextEmbedding:
    # Load only from the folder bundled with the backend; never download at runtime.
    return TextEmbedding(
        model_name=os.environ["EMBEDDING_MODEL"],
        specific_model_path=str(BACKEND_DIR / os.environ["EMBEDDING_MODEL_DIR"]),
        local_files_only=True,
    )


def embed_passages(texts: list[str]) -> list:
    # Small batches avoid padding every text to the longest one in the batch.
    batch_size = int(os.environ["EMBEDDING_BATCH_SIZE"])
    return list(_model().passage_embed(texts, batch_size=batch_size))


def embed_query(text: str):
    return next(_model().query_embed(text))
