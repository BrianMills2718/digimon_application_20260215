#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import numpy as np

INDEX_DIR = Path(__file__).resolve().parent
INDEX_PATH = INDEX_DIR / "corpus_embeds.npz"
META_PATH = INDEX_DIR / "corpus_meta.json"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def _load_corpus(corpus_path: Path):
    rows = []
    with corpus_path.open() as f:
        for i, line in enumerate(f):
            obj = json.loads(line)
            title = obj.get("title", "")
            content = obj.get("content", "")
            text = (title + "\n" + content).strip()
            rows.append({"line": i + 1, "title": title, "content": content, "text": text})
    return rows


def build_index(corpus_path: Path):
    from sentence_transformers import SentenceTransformer
    rows = _load_corpus(corpus_path)
    texts = [r["text"] for r in rows]
    model = SentenceTransformer(MODEL_NAME)
    emb = model.encode(texts, batch_size=128, show_progress_bar=False, normalize_embeddings=True)
    emb = np.asarray(emb, dtype=np.float32)
    np.savez_compressed(INDEX_PATH, embeddings=emb)
    with META_PATH.open("w") as f:
        json.dump(
            [{"line": r["line"], "title": r["title"], "content": r["content"]} for r in rows],
            f,
            ensure_ascii=False,
        )
    print(f"built index: {len(rows)} rows, dim={emb.shape[1]}")


def query(q: str, top_k: int):
    from sentence_transformers import SentenceTransformer
    if not INDEX_PATH.exists() or not META_PATH.exists():
        raise SystemExit("index files missing; run: python vector_search.py --build")
    arr = np.load(INDEX_PATH)["embeddings"]
    with META_PATH.open() as f:
        meta = json.load(f)
    model = SentenceTransformer(MODEL_NAME)
    qv = model.encode([q], normalize_embeddings=True)
    qv = np.asarray(qv, dtype=np.float32)[0]
    scores = arr @ qv
    idx = np.argsort(scores)[::-1][:top_k]
    out = []
    for rank, i in enumerate(idx, 1):
        m = meta[int(i)]
        c = m.get("content", "")
        out.append(
            {
                "rank": rank,
                "score": float(scores[int(i)]),
                "line": m.get("line"),
                "title": m.get("title"),
                "snippet": c[:420],
            }
        )
    print(json.dumps({"query": q, "top_k": top_k, "results": out}, ensure_ascii=False))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true")
    p.add_argument("--corpus", default="corpus.jsonl")
    p.add_argument("--query", default=None)
    p.add_argument("--top-k", type=int, default=8)
    args = p.parse_args()

    corpus_path = Path(args.corpus)
    if args.build:
        build_index(corpus_path)
        return
    if not args.query:
        raise SystemExit("provide --query or --build")
    query(args.query, args.top_k)


if __name__ == "__main__":
    main()
