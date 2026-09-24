"""Local text embeddings (fastembed, BAAI/bge-small-en-v1.5, 384-d). No API key."""

from functools import lru_cache

MODEL = "BAAI/bge-small-en-v1.5"
DIM = 384


@lru_cache
def _model():
    from fastembed import TextEmbedding
    return TextEmbedding(MODEL)


def embed_passages(texts: list[str]) -> list[list[float]]:
    return [v.tolist() for v in _model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    return next(iter(_model().query_embed([text]))).tolist()
