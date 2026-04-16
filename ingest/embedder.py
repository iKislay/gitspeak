import uuid
import logging
from typing import List, Dict, Any
from openai import OpenAI
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import OLLAMA_API_KEY, OLLAMA_BASE_URL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME, OLLAMA_EMBED_MODEL

logger = logging.getLogger(__name__)

class Embedder:
    """
    Handles generating embeddings via Ollama Cloud (OpenAI-compatible) and upserting into Qdrant.
    """
    def __init__(self):
        # We use the OpenAI client with the Ollama endpoint
        self.client = OpenAI(
            api_key=OLLAMA_API_KEY,
            base_url=OLLAMA_BASE_URL
        )
        self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
        
        # Ensure collection exists
        self._init_collection()

    def _init_collection(self):
        try:
            # Check if collection exists
            if not self.qdrant_client.collection_exists(COLLECTION_NAME):
                # Note: Vector size depends on the model.
                # 'nomic-embed-text' typically has 768 dimensions.
                # If using something else, this might need dynamic configuration.
                # Assuming standard Nomics 768 for Ollama-based embeddings.
                vector_size = 768 if "nomic" in OLLAMA_EMBED_MODEL.lower() else 1536
                
                self.qdrant_client.create_collection(
                    collection_name=COLLECTION_NAME,
                    vectors_config=models.VectorParams(
                        size=vector_size,
                        distance=models.Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {COLLECTION_NAME} with size {vector_size}")
            else:
                logger.info(f"Qdrant collection {COLLECTION_NAME} already exists.")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collection: {e}")

    def embed_and_upsert(self, chunks: List[Dict[str, Any]], batch_size: int = 100):
        total_chunks = len(chunks)
        logger.info(f"Starting embed and upsert for {total_chunks} chunks using {OLLAMA_EMBED_MODEL}...")

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk["text"] for chunk in batch]
            
            try:
                # Embed batch
                response = self.client.embeddings.create(
                    input=texts,
                    model=OLLAMA_EMBED_MODEL
                )
                embeddings = [data.embedding for data in response.data]
                
                # Prepare Qdrant points
                points = []
                for idx, chunk in enumerate(batch):
                    # Deterministic UUID from repo_slug+id+chunk_index
                    unique_string = f"{chunk.get('repo', 'unknown')}_{chunk.get('id', 'unknown')}_{chunk.get('chunk_index', 0)}"
                    point_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, unique_string))
                    
                    points.append(
                        models.PointStruct(
                            id=point_id,
                            vector=embeddings[idx],
                            payload=chunk  # Includes text and all metadata
                        )
                    )
                
                # Upsert batch
                self.qdrant_client.upsert(
                    collection_name=COLLECTION_NAME,
                    points=points
                )
                logger.info(f"Upserted items {i} to {i + len(batch)}.")
            except Exception as e:
                logger.error(f"Failed to process batch at index {i}: {e}")

        logger.info(f"Upserted {total_chunks} points to Qdrant.")
