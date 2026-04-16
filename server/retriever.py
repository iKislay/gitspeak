import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import GOOGLE_API_KEY, GEMINI_EMBED_MODEL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME

logger = logging.getLogger(__name__)

class Retriever:
    """
    Handles query embedding via Gemini and semantic retrieval from Qdrant.
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
                    field_schema=models.PayloadSchemaType.KEYWORD
                )
                logger.info("Ensured keyword index on 'repo' field.")
        except Exception as e:
            logger.warning(f"Could not ensure repo index: {e}")

    def search(self, query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Embed the query and search Qdrant for matching chunks filtered by repo.
        """
        # Normalize repo name (strip whitespace)
        repo = repo.strip()
        logger.info(f"Retrieving context for query: '{query}' in repo: '{repo}'")

        try:
            # Embed query using Gemini
            response = self.genai_client.models.embed_content(
                model=GEMINI_EMBED_MODEL,
                contents=query,
                config=types.EmbedContentConfig(task_type="RETRIEVAL_QUERY")
            )
            query_vector = response.embeddings[0].values

            # Search Qdrant using the newer query_points API
            hits = self.qdrant_client.query_points(
                collection_name=COLLECTION_NAME,
                query=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchValue(value=repo)
                        )
                    ]
                ),
                limit=top_k
            ).points
            
            results = []
            for hit in hits:
                if hit.payload and isinstance(hit.payload, dict):
                    results.append(hit.payload)
                    
            logger.info(f"Retrieved {len(results)} context chunks.")
            return results

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def list_indexed_repos(self) -> List[str]:
        """
        Scans Qdrant to find all unique 'repo' values.
        """
        try:
            repos = set()
            offset = None
            
            # Make sure collection exists
            if not self.qdrant_client.collection_exists(COLLECTION_NAME):
                return []

            while True:
                response = self.qdrant_client.scroll(
                    collection_name=COLLECTION_NAME,
                    scroll_filter=None,
                    limit=1000,
                    offset=offset,
                    with_payload=["repo"],
                    with_vectors=False
                )
                points, offset = response
                
                for point in points:
                    if point.payload and "repo" in point.payload:
                        repos.add(point.payload["repo"])
                        
                if offset is None:
                    break
                    
            return list(repos)
        except Exception as e:
            logger.error(f"Failed to list indexed repos: {e}")
            return []

# Singleton instance
retriever = Retriever()

def search(query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
    return retriever.search(query, repo, top_k)

def list_indexed_repos() -> List[str]:
    return retriever.list_indexed_repos()
