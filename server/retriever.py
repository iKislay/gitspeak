import logging
from typing import List, Dict, Any
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME, OLLAMA_EMBED_MODEL

logger = logging.getLogger(__name__)

class Retriever:
    """
    Handles query embedding via Ollama and semantic retrieval from Qdrant.
    """
    def __init__(self):
        self.client = OpenAI(
            api_key=OLLAMA_API_KEY,
            base_url=OLLAMA_BASE_URL
        )
        self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

    def search(self, query: str, repo: str, top_k: int = 6) -> List[Dict[str, Any]]:
        """
        Embed the query and search Qdrant for matching chunks filtered by repo.
        """
        logger.info(f"Retrieving context for query: '{query}' in repo: {repo}")
        
        try:
            # Embed query
            response = self.client.embeddings.create(
                input=[query],
                model=OLLAMA_EMBED_MODEL
            )
            query_vector = response.data[0].embedding

            # Search Qdrant
            hits = self.qdrant_client.search(
                collection_name=COLLECTION_NAME,
                query_vector=query_vector,
                query_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="repo",
                            match=models.MatchValue(value=repo)
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
                    if "repo" in point.payload:
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
