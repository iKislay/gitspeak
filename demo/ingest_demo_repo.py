import sys
import os
import logging

# Ensure root directory is in import path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.github_fetcher import GithubFetcher
from ingest.chunker import Chunker
from ingest.embedder import Embedder

def main():
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("demo_ingest")
    
    # Hardcoded repo as requested for the demo script
    repo = "facebook/react"
    logger.info(f"Starting ingestion pipeline for demo repo: {repo}")

    try:
        # 1. Fetch
        logger.info("Step 1: Fetching data from GitHub...")
        fetcher = GithubFetcher()
        raw_items = fetcher.fetch_all(repo)
        
        if not raw_items:
            logger.warning("No items fetched. Check your GITHUB_TOKEN or rate limits.")
            return

        # 2. Chunk
        logger.info("Step 2: Processing chunks...")
        chunker = Chunker()
        chunks = chunker.process(raw_items)
        
        # 3. Embed & Upsert
        logger.info("Step 3: Embedding and Upserting to Qdrant...")
        embedder = Embedder()
        embedder.embed_and_upsert(chunks)
        
        logger.info("Demo ingestion complete!")

    except Exception as e:
        logger.error(f"Demo ingestion failed: {e}")

if __name__ == "__main__":
    main()
