"""BM25 lexical retrieval for improved query-document matching."""

import math
from collections import Counter

from itlr.core.recommender import tokenize


class BM25Index:
    """Okapi BM25 index over tokenized documents."""

    def __init__(self, k1=1.4, b=0.75):
        self.k1 = k1
        self.b = b
        self.doc_lengths = []
        self.avgdl = 0.0
        self.doc_freqs = []
        self.idf = {}
        self.n_docs = 0

    def fit(self, documents):
        """Build BM25 statistics from raw text documents."""
        self.n_docs = len(documents)
        self.doc_freqs = []
        df_counter = Counter()
        self.doc_lengths = []

        for doc in documents:
            tokens = tokenize(doc)
            self.doc_lengths.append(len(tokens))
            tf = Counter(tokens)
            self.doc_freqs.append(tf)
            df_counter.update(set(tokens))

        self.avgdl = sum(self.doc_lengths) / max(self.n_docs, 1)

        for term, df in df_counter.items():
            self.idf[term] = math.log(1 + (self.n_docs - df + 0.5) / (df + 0.5))

        return self

    def score_query(self, query):
        """Return BM25 scores for all documents given a query string."""
        query_tokens = tokenize(query)
        if not query_tokens:
            return [0.0] * self.n_docs

        scores = [0.0] * self.n_docs
        for token in set(query_tokens):
            if token not in self.idf:
                continue
            idf = self.idf[token]
            for i, tf_map in enumerate(self.doc_freqs):
                freq = tf_map.get(token, 0)
                if freq == 0:
                    continue
                dl = self.doc_lengths[i]
                denom = freq + self.k1 * (1 - self.b + self.b * dl / self.avgdl)
                scores[i] += idf * (freq * (self.k1 + 1)) / denom

        return scores

    def normalize_scores(self, scores):
        """Min-max normalize scores to [0, 1]."""
        if not scores:
            return scores
        lo, hi = min(scores), max(scores)
        if hi == lo:
            return [0.0] * len(scores)
        return [(s - lo) / (hi - lo) for s in scores]
