import uuid
import logging
from typing import List, Dict, Any
from google import genai
from google.genai import types
from qdrant_client import QdrantClient
from qdrant_client.http import models

from config import GOOGLE_API_KEY, GEMINI_EMBED_MODEL, QDRANT_URL, QDRANT_API_KEY, COLLECTION_NAME

logger = logging.getLogger(__name__)

class Embedder:
    """
    Handles generating embeddings via Gemini and upserting into Qdrant.
    """
    def __init__(self):
        self.genai_client = genai.Client(api_key=GOOGLE_API_KEY)
        self.qdrant_client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)

        # Ensure collection exists
        self._init_collection()

    def _init_collection(self):
        try:
            # Check if collection exists
            if not self.qdrant_client.collection_exists(COLLECTION_NAME):
                # gemini-embedding-001 has 3072 dimensions
                vector_size = 3072

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

            # Ensure keyword index exists on 'repo' field (required for filtered search)
            self.qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name="repo",
                field_schema=models.PayloadSchemaType.KEYWORD
            )
            logger.info("Ensured keyword index on 'repo' field.")
        except Exception as e:
            logger.error(f"Failed to initialize Qdrant collection: {e}")

    def embed_and_upsert(self, chunks: List[Dict[str, Any]], batch_size: int = 100):
        total_chunks = len(chunks)
        logger.info(f"Starting embed and upsert for {total_chunks} chunks using {GEMINI_EMBED_MODEL}...")

        for i in range(0, total_chunks, batch_size):
            batch = chunks[i:i + batch_size]
            texts = [chunk["text"] for chunk in batch]
            
            try:
                # Embed batch using Gemini
                response = self.genai_client.models.embed_content(
                    model=GEMINI_EMBED_MODEL,
                    contents=texts,
                    config=types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT")
                )
                embeddings = [e.values for e in response.embeddings]
                
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
