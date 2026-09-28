"""Dense retrieval: embed chunks once, rank by cosine similarity to the query embedding.

Keyword search cannot connect a touchdown sensor to a gyro that tripped fault protection; both
are "a spurious input triggered an irreversible action", which is the kind of match an embedding
model can make. Embeddings are cached per model under data/interim/embeddings, keyed by chunk id,
so rebuilding chunks invalidates them automatically.

    python -m lore.retrieve.dense   # build (or refresh) the embedding cache
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from lore.paths import DATA_DIR
from lore.retrieve.bm25 import CHUNKS_PATH, Hit

EMBED_DIR = DATA_DIR / "interim" / "embeddings"
DEFAULT_MODEL = "BAAI/bge-base-en-v1.5"
# bge models are trained with this instruction on the query side only.
QUERY_PREFIX = {
    "BAAI/bge-base-en-v1.5": "Represent this sentence for searching relevant passages: "
}


def passage_text(chunk: dict) -> str:
    # The context header says which lesson or report the chunk is from; without it a chunk
    # like "Recommendation: verify polarity by test" loses what it is about.
    return f"{chunk['context']}\n\n{chunk['text']}"


def _cache_paths(model_name: str) -> tuple[Path, Path]:
    stem = model_name.replace("/", "__")
    return EMBED_DIR / f"{stem}.npy", EMBED_DIR / f"{stem}.ids.json"


class DenseRetriever:
    def __init__(self, chunks: list[dict], model_name: str = DEFAULT_MODEL, batch_size: int = 32):
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.chunks = chunks
        self.model_name = model_name
        self.name = "dense-" + model_name.split("/")[-1]
        self.model = SentenceTransformer(model_name)
        self.embeddings = self._load_or_build(batch_size)

    @classmethod
    def from_file(cls, path: Path = CHUNKS_PATH, **kwargs) -> DenseRetriever:
        with path.open(encoding="utf-8") as f:
            return cls([json.loads(line) for line in f], **kwargs)

    def _load_or_build(self, batch_size: int) -> np.ndarray:
        vectors_path, ids_path = _cache_paths(self.model_name)
        ids = [c["id"] for c in self.chunks]
        cached_ids = ids_path.exists() and json.loads(ids_path.read_text(encoding="utf-8"))
        if cached_ids == ids and vectors_path.exists():
            return np.load(vectors_path)
        vectors = self.model.encode(
            [passage_text(c) for c in self.chunks],
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=True,
            convert_to_numpy=True,
        ).astype(np.float32)
        EMBED_DIR.mkdir(parents=True, exist_ok=True)
        np.save(vectors_path, vectors)
        ids_path.write_text(json.dumps(ids), encoding="utf-8")
        return vectors

    def search(self, query: str, k: int = 20, before: str | None = None) -> list[Hit]:
        prefix = QUERY_PREFIX.get(self.model_name, "")
        q = self.model.encode(prefix + query, normalize_embeddings=True, convert_to_numpy=True)
        scores = self.embeddings @ q.astype(np.float32)
        hits = []
        for i in np.argsort(-scores):
            chunk = self.chunks[i]
            if before and not chunk["available_from"] < before:
                continue
            hits.append(Hit(chunk["id"], chunk["doc_id"], float(scores[i]), chunk))
            if len(hits) == k:
                break
        return hits


if __name__ == "__main__":
    retriever = DenseRetriever.from_file()
    print(f"{retriever.embeddings.shape[0]} chunks embedded with {retriever.model_name}")
