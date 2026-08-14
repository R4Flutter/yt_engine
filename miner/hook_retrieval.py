"""M3 Hook retrieval — semantic + DNA + evidence weighted lookup (Phase 6).

Given a topic, retrieve successful hooks by MORE than semantic text
similarity. The final score stacks:

    retrieval = 0.30 * semantic  (char-ngram TF-IDF cosine)
              + 0.20 * topic     (niche match)
              + 0.15 * dna       (Hook DNA similarity)
              + 0.20 * outlier   (how extreme the video's outlier score is)
              + 0.15 * retention (how well the hook window held viewers)

Embeddings are deterministic char-ngram TF-IDF (sklearn, already installed)
— no model download, fits the ~1 GB free RAM constraint. Weights are
configurable via settings.yaml [hooks][retrieval].

Scientific rules:
  * never present retrieved hooks as templates to copy — they are evidence
    for pattern extraction, not sentences to clone
"""

from __future__ import annotations

import math
import pickle
from collections import Counter
from difflib import SequenceMatcher

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer

from miner.hook_dna import extract_dna

VEC_PARAMS = dict(analyzer="char_wb", ngram_range=(2, 5),
                  max_features=8000, sublinear_tf=True)

DEFAULT_WEIGHTS = {
    "semantic": 0.30, "topic": 0.20, "dna": 0.15,
    "outlier": 0.20, "retention": 0.15,
}


def _dna_sim(a: dict, b: dict) -> float:
    """Jaccard-ish overlap over the Hook DNA keys that matter."""
    keys = ("opening_device", "curiosity_mechanism", "emotional_mechanism",
            "stakes_type", "promise_type")
    same = sum(1 for k in keys if a.get(k) and a.get(k) == b.get(k))
    return same / len(keys)


def build_embedder(texts: list[str]) -> TfidfVectorizer:
    vec = TfidfVectorizer(**VEC_PARAMS)
    vec.fit(texts or ["seed"])
    return vec


def embed(vec: TfidfVectorizer, text: str) -> bytes:
    """Deterministic embedding stored as pickled sparse matrix in the DB."""
    m = vec.transform([text])
    return pickle.dumps(m)


def cosine(a: bytes, b: bytes) -> float:
    """Cosine between two pickled TF-IDF sparse rows (storage format)."""
    x = pickle.loads(a)
    y = pickle.loads(b)
    return cosine_sparse(x, y)


def _norm(v) -> float:
    return float(np.sqrt(v.multiply(v).sum()))


def cosine_sparse(x, y, nx: float | None = None, ny: float | None = None) -> float:
    """Cosine between two in-memory sparse rows, norms precomputed."""
    nx = nx if nx is not None else _norm(x)
    ny = ny if ny is not None else _norm(y)
    if nx == 0 or ny == 0:
        return 0.0
    return float(x.multiply(y).sum() / (nx * ny))


class SimIndex:
    """In-memory cosine index over a set of texts with ONE shared embedder.

    All texts are embedded in a single batch transform; similarity to a query
    is one matrix-vector dot with precomputed norms. This replaces the old
    per-pair pickle+multiply path (~100x fewer scipy ops).
    """

    def __init__(self, texts: list[str]):
        self.vec = build_embedder(texts) if texts else None
        if self.vec is None:
            self._M = self._norms = None
        else:
            self._M = self.vec.transform(texts)
            self._norms = np.sqrt(
                np.asarray(self._M.multiply(self._M).sum(axis=1)).ravel())

    @property
    def n(self) -> int:
        return 0 if self._M is None else self._M.shape[0]

    def sims(self, text: str) -> list[float]:
        """Cosine of `text` against every indexed text, in index order."""
        if self._M is None:
            return []
        q = self.vec.transform([text])
        nq = _norm(q)
        if nq == 0:
            return [0.0] * self.n
        dots = np.asarray(self._M.dot(q.T).toarray()).ravel()
        nz = self._norms > 0
        out = np.zeros(self.n)
        out[nz] = dots[nz] / (nq * self._norms[nz])
        return [float(v) for v in out]

    def sims_many(self, texts: list[str]) -> list[list[float]]:
        return [self.sims(t) for t in texts]


def retrieve(conn, topic: str, dna: dict | None = None, niche: str | None = None,
             top_k: int = 8, weights: dict | None = None,
             max_per_channel: int | None = None) -> list[dict]:
    """Weighted retrieval over hook_library.

    Channel-balanced: a single dominant channel must not monopolize the
    evidence set. Near-duplicate texts are dropped (a template said 50x
    across videos is one datum, not fifty).

    Returns rows enriched with retrieval_score, already sorted best-first.
    """
    w = weights or DEFAULT_WEIGHTS
    rows = conn.execute(
        """SELECT id, video_id, channel, hook_text, niche_tag, outlier_score,
                  opening_device, curiosity_mechanism, emotional_mechanism,
                  stakes_type, promise_type, narrative_structure,
                  retention_3s, retention_10s, embedding
           FROM hook_library
           WHERE hook_text IS NOT NULL AND embedding IS NOT NULL""").fetchall()
    if not rows:
        return []

    idx = SimIndex([r["hook_text"] for r in rows])
    sem_scores = idx.sims(topic)
    qdna = dna or extract_dna(topic)

    # normalize outlier scores 0..1 across the candidate set
    outs = [r["outlier_score"] or 0 for r in rows]
    omax = max(outs) or 1.0

    scored = []
    for r, sem in zip(rows, sem_scores):
        top = 1.0 if (niche and r["niche_tag"] == niche) else 0.0
        dn = _dna_sim(qdna, {
            "opening_device": r["opening_device"],
            "curiosity_mechanism": r["curiosity_mechanism"],
            "emotional_mechanism": r["emotional_mechanism"],
            "stakes_type": r["stakes_type"],
            "promise_type": r["promise_type"],
        })
        out = (r["outlier_score"] or 0) / omax
        ret = max(0.0, min(1.0, ((r["retention_10s"] or 0) + 1) / 2))  # z -> 0..1
        score = (w["semantic"] * sem + w["topic"] * top + w["dna"] * dn +
                 w["outlier"] * out + w["retention"] * ret)
        scored.append({**dict(r), "retrieval_score": round(score, 4)})

    scored.sort(key=lambda r: -r["retrieval_score"])

    # channel balance: uniform share, minimum 1 per channel
    n_channels = len({r["channel"] for r in scored if r["channel"]})
    if max_per_channel is None:
        max_per_channel = max(1, math.ceil(top_k / max(1, n_channels)))

    selected: list[dict] = []
    seen_channels: Counter = Counter()
    for r in scored:
        ch = r["channel"]
        if ch and seen_channels[ch] >= max_per_channel:
            continue
        if any(SequenceMatcher(None, r["hook_text"].lower(),
                               s["hook_text"].lower()).ratio() > 0.9
               for s in selected):
            continue  # near-duplicate evidence adds no information
        seen_channels[ch] += 1
        selected.append(r)
        if len(selected) >= top_k:
            break
    return selected