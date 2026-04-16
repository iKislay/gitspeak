import logging
from typing import List, Dict, Any, Optional
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import GOOGLE_API_KEY, GEMINI_EMBED_MODEL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME

logger = logging.getLogger(__name__)


class Retriever:
    """
    Handles query embedding via Gemini and semantic retrieval from Qdrant.
    Supports both per-repo filtered search and cross-repository search.
    """

    def __init__(self):
        self.genai_client = genai.Client(api_key=GOOGLE_API_KEY)
        self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        self._ensure_index()

    def _ensure_index(self):
        """Ensure keyword index on 'repo' field exists (required for filtered search)."""
        try:
            if self.qdrant_client.collection_exists(COLLECTION_NAME):
                self.qdrant_client.create_payload_index(
                    collection_name=COLLECTION_NAME,
                    field_name="repo",
                    field_schema=models.PayloadSchemaType.KEYWORD,
                )
                logger.info("Ensured keyword index on 'repo' field.")
        except Exception as e:
            logger.warning(f"Could not ensure repo index: {e}")

    def _embed_query(self, query: str) -> List[float]:
        """Embed a query string via Gemini and return the vector."""
        response = self.genai_client.models.embed_content(
            model=GEMINI_EMBED_MODEL,
            contents=query,
            config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return response.embeddings[0].values

    def search(self, query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Embed the query and search Qdrant for matching chunks filtered by repo.
        """
        repo = repo.strip()
        logger.info(f"Retrieving context for query: '{query}' in repo: '{repo}'")

        try:
            query_vector = self._embed_query(query)

            hits = self.qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchValue(value=repo),
                        )
                    ]
                ),
                limit=top_k,
            ).points

            results = [hit.payload for hit in hits if hit.payload and isinstance(hit.payload, dict)]
            logger.info(f"Retrieved {len(results)} context chunks from {repo}.")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def search_across_repos(
        self,
        query: str,
        repos: Optional[List[str]] = None,
        top_k: int = 8,
    ) -> List[Dict[str, Any]]:
        """
        Search across all indexed repos (or a specified subset).
        Returns the top_k most relevant chunks ranked globally, each tagged with its repo.
        """
        logger.info(f"Cross-repo search for: '{query}' across repos: {repos}")

        try:
            query_vector = self._embed_query(query)

            # Optional: filter to only the listed repos using a Should filter
            query_filter = None
            if repos:
                query_filter = models.Filter(
                    should=[
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchValue(value=r),
                        )
                        for r in repos
                    ]
                )

            hits = self.qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=query_filter,
                limit=top_k,
            ).points

            results = [hit.payload for hit in hits if hit.payload and isinstance(hit.payload, dict)]
            logger.info(f"Cross-repo search returned {len(results)} chunks.")
            return results

        except Exception as e:
            logger.error(f"Cross-repo search failed: {e}")
            return []

    def list_indexed_repos(self) -> List[str]:
        """Scans Qdrant to find all unique 'repo' values."""
        try:
            repos = set()
            offset = None

            if not self.qdrant_client.collection_exists(COLLECTION_NAME):
                return []

            while True:
                response = self.qdrant_client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=None,
                    limit=1000,
                    offset=offset,
                    with_payload=["repo"],
                    with_vectors=False,
                )
                points, offset = response

                for point in points:
                    if point.payload and "repo" in point.payload:
                        repos.add(point.payload["repo"])

                if offset is None:
                    break

            return sorted(repos)
        except Exception as e:
            logger.error(f"Failed to list indexed repos: {e}")
            return []

    def repo_stats(self) -> Dict[str, int]:
        """Returns a dict mapping repo_slug -> chunk count."""
        try:
            counts: Dict[str, int] = {}
            offset = None

            if not self.qdrant_client.collection_exists(COLLECTION_NAME):
                return {}

            while True:
                response = self.qdrant_client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=None,
                    limit=1000,
                    offset=offset,
                    with_payload=["repo"],
                    with_vectors=False,
                )
                points, offset = response
                for point in points:
                    repo = (point.payload or {}).get("repo")
                    if repo:
                        counts[repo] = counts.get(repo, 0) + 1
                if offset is None:
                    break

            return counts
        except Exception as e:
            logger.error(f"Failed to compute repo stats: {e}")
            return {}


# Module-level singletons
# (the Optional import is needed at module scope for the type hint in search_across_repos)
from typing import Optional

retriever = Retriever()


def search(query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
    return retriever.search(query, repo, top_k)


def search_across_repos(
    query: str,
    repos: Optional[List[str]] = None,
    top_k: int = 8,
) -> List[Dict[str, Any]]:
    return retriever.search_across_repos(query, repos, top_k)


def list_indexed_repos() -> List[str]:
    return retriever.list_indexed_repos()


def repo_stats() -> Dict[str, int]:
    return retriever.repo_stats()
