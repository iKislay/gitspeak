import logging
from typing import List, Dict, Any
import google.generativeai as genai
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import GOOGLE_API_KEY, GEMINI_EMBED_MODEL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME

logger = logging.getLogger(__name__)

class Retriever:
    """
    Handles query embedding via Gemini and semantic retrieval from Qdrant.
    """
    def __init__(self):
        genai.configure(api_key=GOOGLE_API_KEY)
        self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    def search(self, query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Embed the query and search Qdrant for matching chunks filtered by repo.
        """
        # Normalize repo name (strip whitespace)
        repo = repo.strip()
        logger.info(f"Retrieving context for query: '{query}' in repo: '{repo}'")
        
        try:
            # Embed query using Gemini
            response = genai.embed_content(
                model=GEMINI_EMBED_MODEL,
                content=query,
                task_type="retrieval_query"
            )
            query_vector = response['embedding']

            # Search Qdrant
            hits = self.qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=models.Filter(
                    should=[ # Changed must to should with a fallback or just be more lenient
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchValue(value=repo)
                        ),
                        # Fallback for case sensitivity or minor variations
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchText(text=repo)
                        )
                    ]
                ),
                limit=top_k
            )
            
            results = []
            for hit in hits:
                if isinstance(hit.payload, dict):
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
