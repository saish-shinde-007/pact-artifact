"""Trained screener that gates which log entries reach adjudication; its recall
bounds what the jury ever sees.
"""
import math
from collections import defaultdict

from neutral_detectors import _norm


def features(text: str, n: int = 4):
    t = text.lower()
    feats = [f"w:{w}" for w in t.split()]
    norm = _norm(t)
    feats += [f"c:{norm[i:i + n]}" for i in range(max(0, len(norm) - n + 1))]
    return feats


class Screener:
    """Fitted rung-0 pre-filter. Tuned for recall: whatever it does not flag is
    auto-cleared, so a miss is a pipeline false negative."""

    def __init__(self, n: int = 4):
        self.n = n
        self.logprior = {0: 0.0, 1: 0.0}
        self.loglik = {0: {}, 1: {}}
        self.default = {0: 0.0, 1: 0.0}
        self.threshold = 0.0

    def fit(self, items, target_recall: float = 0.99):
        counts = {0: defaultdict(int), 1: defaultdict(int)}
        totals = {0: 0, 1: 0}
        docs = {0: 0, 1: 0}
        vocab = set()
        for it in items:
            c = it["label"]
            docs[c] += 1
            for f in features(it["text"], self.n):
                counts[c][f] += 1
                totals[c] += 1
                vocab.add(f)
        v = len(vocab)
        n_docs = docs[0] + docs[1]
        for c in (0, 1):
            self.logprior[c] = math.log(docs[c] / n_docs) if docs[c] else -1e9
            self.default[c] = math.log(1.0 / (totals[c] + v)) if v else 0.0
            self.loglik[c] = {f: math.log((counts[c][f] + 1) / (totals[c] + v))
                              for f in vocab}
        # pick the decision threshold on TRAINING data only
        scores = sorted(self.score(it["text"]) for it in items if it["label"] == 1)
        if scores:
            idx = min(len(scores) - 1, int((1 - target_recall) * len(scores)))
            self.threshold = scores[idx] - 1e-9
        return self

    def score(self, text: str) -> float:
        """Log-odds that the action violates policy."""
        s = self.logprior[1] - self.logprior[0]
        for f in features(text, self.n):
            s += self.loglik[1].get(f, self.default[1])
            s -= self.loglik[0].get(f, self.default[0])
        return s

    def flag(self, text: str) -> bool:
        return self.score(text) > self.threshold
