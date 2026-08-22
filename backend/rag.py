from pathlib import Path
from typing import List, Dict
import re
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


def read_documents(folder: Path) -> List[Dict]:
    docs = []

    if not folder.exists():
        return docs

    for path in folder.rglob("*"):
        if not path.is_file():
            continue

        if path.suffix.lower() in {".txt", ".md"}:
            text = path.read_text(encoding="utf-8", errors="ignore")
            docs.append({"source": str(path), "text": text})

    return docs


class LocalRAG:
    """
    Lightweight local RAG for the hackathon MVP.
    For PDF-heavy production use, add PDF text extraction/OCR and embeddings.
    """

    def __init__(self, docs: List[Dict]):
        self.docs = docs
        self.vectorizer = None
        self.matrix = None

        if docs:
            self.vectorizer = TfidfVectorizer(
                lowercase=True,
                ngram_range=(1, 2),
                max_features=20000,
            )
            self.matrix = self.vectorizer.fit_transform(
                [d["text"] for d in docs]
            )

    def retrieve(self, query: str, top_k: int = 3) -> List[Dict]:
        if not self.docs or self.matrix is None:
            return []

        q = self.vectorizer.transform([query])
        scores = cosine_similarity(q, self.matrix)[0]
        indexes = np.argsort(scores)[::-1][:top_k]

        results = []
        for i in indexes:
            if scores[i] <= 0:
                continue

            text = self.docs[i]["text"]
            results.append({
                "source": self.docs[i]["source"],
                "score": float(scores[i]),
                "snippet": text[:3000],
            })

        return results
