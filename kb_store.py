# -*- coding: utf-8 -*-
"""Chroma 本地向量库封装（新版 PersistentClient）。

向量由 Gemini gemini-embedding-001 生成；旧版 Azure embedding 建的 vs/
数据库不能复用，2.0 首次运行会重建。
每段存来源 metadata：{"source": 词条/文件名, "chunk": 段号, "total": 总段数}。
"""

import hashlib
import os

import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

COLLECTION_NAME = "knowledge_base"


def _source_id(source_name: str) -> str:
    return hashlib.md5(source_name.encode("utf-8")).hexdigest()[:12]


class GeminiEmbeddingFunction(EmbeddingFunction):
    """用 google-genai 生成向量的 Chroma embedding function。"""

    def __init__(self, gemini_client):
        self._gemini = gemini_client

    def __call__(self, input: Documents) -> Embeddings:
        return self._gemini.embed_texts(list(input))

    def name(self) -> str:
        return "gemini-embedding-001"


class KBStore:
    def __init__(self, db_dir: str, gemini_client):
        os.makedirs(db_dir, exist_ok=True)
        self._db_dir = db_dir
        self._embed_model = gemini_client.embed_model
        self._ensure_fresh_db()
        self._client = chromadb.PersistentClient(path=db_dir)
        embed_fn = GeminiEmbeddingFunction(gemini_client)
        try:
            self.collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=embed_fn,
                configuration={"hnsw": {"space": "cosine"}},
            )
        except TypeError:
            # 旧版 chromadb 用 metadata 传 hnsw 参数
            self.collection = self._client.get_or_create_collection(
                name=COLLECTION_NAME,
                embedding_function=embed_fn,
                metadata={"hnsw:space": "cosine"},
            )

    def add_entry(self, source_name: str, chunks: list) -> int:
        """写入一个词条的全部段；重复学习会先删旧段再写入。返回写入段数。"""
        sid = _source_id(source_name)
        existing = self.collection.get(
            where={"source": source_name}, include=[]
        )
        if existing["ids"]:
            self.collection.delete(ids=existing["ids"])
        ids = [f"{sid}-{i:04d}" for i in range(len(chunks))]
        metadatas = [
            {"source": source_name, "chunk": i, "total": len(chunks)}
            for i in range(len(chunks))
        ]
        self.collection.add(documents=list(chunks), metadatas=metadatas, ids=ids)
        return len(chunks)

    def query(self, question: str, top_k: int = 3) -> list:
        """返回 [{"text", "source", "chunk", "distance"}]，按距离从小到大。"""
        if self.collection.count() == 0:
            return []
        res = self.collection.query(
            query_texts=[question],
            n_results=min(top_k, self.collection.count()),
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append({
                "text": doc,
                "source": meta.get("source", "?"),
                "chunk": meta.get("chunk", 0),
                "distance": float(dist),
            })
        return out

    def list_sources(self) -> list:
        """返回 [(来源名, 段数)]，按来源名排序。"""
        data = self.collection.get(include=["metadatas"])
        counts = {}
        for meta in data["metadatas"]:
            name = meta.get("source", "?")
            counts[name] = counts.get(name, 0) + 1
        return sorted(counts.items())

    def _ensure_fresh_db(self):
        """向量与 embedding 模型绑定：旧库（Azure embedding 建的）不能复用。

        vs/ 里用 embedding.txt 记录建库模型；标记缺失或不一致时，
        把旧目录改名备份（vs.bak-时间戳），重建空库，并记录备份路径。
        """
        import datetime

        marker = os.path.join(self._db_dir, "embedding.txt")
        self.stale_backup = None
        non_empty = os.path.isdir(self._db_dir) and bool(os.listdir(self._db_dir))
        marker_ok = (
            os.path.exists(marker)
            and open(marker, encoding="utf-8").read().strip() == self._embed_model
        )
        if non_empty and not marker_ok:
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            backup = f"{self._db_dir.rstrip(os.sep)}.bak-{stamp}"
            os.rename(self._db_dir, backup)
            os.makedirs(self._db_dir, exist_ok=True)
            self.stale_backup = backup
        with open(marker, "w", encoding="utf-8") as f:
            f.write(self._embed_model)

    def count(self) -> int:
        return self.collection.count()
