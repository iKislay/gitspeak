import logging
from fastapi import FastAPI, Request, BackgroundTasks
from pydantic import BaseModel

from server.vapi_handler import process_webhook
from server.retriever import list_indexed_repos

from ingest.github_fetcher import GithubFetcher
from ingest.chunker import Chunker
from ingest.embedder import Embedder

# Configure standard logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Voice Codebase Oracle")

class IngestRequest(BaseModel):
    repo: str

@app.get("/health")
async def health_check():
    """Health check returning indexed repos to verify working state."""
    repos = list_indexed_repos()
    return {
        "status": "ok",
        "indexed_repos": repos
    }

@app.post("/webhook")
async def vapi_webhook(request: Request):
    """Event handler for all VAPI webhooks."""
    try:
        body = await request.json()
        logger.info(f"Received VAPI webhook: {body.get('message', {}).get('type')}")
        response = await process_webhook(request)
        return response
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        return {"error": str(e)}

@app.post("/ingest")
async def ingest_repo(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Triggers synchronous (or optionally background) ingestion of a repository.
    Hackathon scope: Synchronous is fine, but can use background_tasks to avoid timeout.
    """
    def run_ingestion(repo_slug: str):
        try:
            logger.info(f"Starting manual ingestion pipeline for {repo_slug}")
            fetcher = GithubFetcher()
            raw_items = fetcher.fetch_all(repo_slug)
            
            chunker = Chunker()
            chunks = chunker.process(raw_items)
            
            embedder = Embedder()
            embedder.embed_and_upsert(chunks)
            logger.info(f"Successfully ingested {repo_slug}")
        except Exception as e:
             logger.error(f"Ingestion pipeline failed for {repo_slug}: {e}")

    # To keep it completely synchronous as per instructions (fine for hackathon):
    run_ingestion(req.repo)
    return {"status": "Ingestion completed successfully for " + req.repo}
