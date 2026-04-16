import logging
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional

from server.vapi_handler import process_webhook, build_vapi_inline_config
from server.retriever import list_indexed_repos, repo_stats
from server.standup import generate_standup_summary
import server.state as state

from ingest.github_fetcher import GithubFetcher
from ingest.chunker import Chunker
from ingest.embedder import Embedder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Voice Codebase Oracle",
    description=(
        "A voice-first AI agent that lets developers query GitHub repositories "
        "using natural speech."
    ),
    version="2.0.0",
)

# Allow the Vercel frontend to reach this backend.
# Restrict allow_origins to your Vercel domain in production for tighter security.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────────────────────────────────────
# Request models
# ─────────────────────────────────────────────────────────────────────────────

class IngestRequest(BaseModel):
    repo: str

class SetRepoRequest(BaseModel):
    repo: str

class StandupRequest(BaseModel):
    repo: Optional[str] = None
    hours: int = 24


# ─────────────────────────────────────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    """Health check with per-repo chunk statistics."""
    stats = repo_stats()
    total_chunks = sum(stats.values())
    return {
        "status": "ok",
        "indexed_repos": sorted(stats.keys()),
        "chunk_counts": stats,
        "total_chunks": total_chunks,
        "active_repo": state.active_repo,
    }


@app.post("/set-repo")
async def set_active_repo(req: SetRepoRequest):
    """Lock the voice assistant to a specific repository."""
    indexed = list_indexed_repos()
    if req.repo not in indexed:
        return {
            "status": "warning",
            "message": f"'{req.repo}' is not indexed yet. Run /ingest first.",
            "active_repo": state.active_repo,
        }
    state.active_repo = req.repo
    logger.info(f"Active repo set to: {req.repo}")
    return {"status": "ok", "active_repo": state.active_repo}


@app.post("/ingest")
async def ingest_repo(req: IngestRequest, background_tasks: BackgroundTasks):
    """
    Triggers ingestion of a GitHub repository. Fetches README, file tree,
    PRs, commits, and actual source file contents, then embeds and stores
    everything in Qdrant.
    """
    def run_ingestion(repo_slug: str):
        try:
            logger.info(f"Ingestion pipeline started for {repo_slug}")
            fetcher = GithubFetcher()
            raw_items = fetcher.fetch_all(repo_slug)

            chunker = Chunker()
            chunks = chunker.process(raw_items)

            embedder = Embedder()
            embedder.embed_and_upsert(chunks)
            logger.info(f"Ingestion complete for {repo_slug}. {len(chunks)} chunks indexed.")
        except Exception as e:
            logger.error(f"Ingestion failed for {repo_slug}: {e}", exc_info=True)

    background_tasks.add_task(run_ingestion, req.repo)
    return {
        "status": "ingestion_started",
        "repo": req.repo,
        "message": (
            f"Ingestion of '{req.repo}' is running in the background. "
            "Check /health to monitor chunk counts."
        ),
    }


@app.post("/standup")
async def standup_report(req: StandupRequest):
    """
    Generate a voice-ready daily standup briefing for a repository.
    Summarises merged PRs, commits, and open PR updates in the last N hours.
    """
    repo = req.repo or state.active_repo
    if not repo:
        return {
            "status": "error",
            "message": "No repo specified. Pass 'repo' in the request body or call /set-repo first.",
        }

    hours = max(1, min(req.hours, 8760))  # clamp between 1 hour and 1 year
    logger.info(f"Generating standup for {repo} (last {hours}h)")

    fetcher = GithubFetcher()
    activity = fetcher.fetch_recent_activity(repo, since_hours=hours)

    if "error" in activity:
        return {"status": "error", "message": activity["error"]}

    summary = generate_standup_summary(activity)

    return {
        "status": "ok",
        "repo": repo,
        "window_hours": hours,
        "summary": summary,
        "raw_activity": {
            "merged_prs": len(activity.get("merged_prs", [])),
            "commits": len(activity.get("commits", [])),
            "open_prs_updated": len(activity.get("open_prs_updated", [])),
        },
    }


@app.get("/vapi-config")
async def vapi_config():
    """
    Return a complete Vapi inline assistant config for the web frontend.
    The frontend passes this directly to vapi.start() so no Vapi dashboard
    assistant setup is required — just a public key.
    """
    return await build_vapi_inline_config()


@app.post("/webhook")
async def vapi_webhook(request: Request):
    """Event handler for all VAPI webhooks (tool-calls, assistant-request, etc.)."""
    try:
        body = await request.json()
        msg_type = body.get("message", {}).get("type")
        logger.info(f"VAPI webhook received: type={msg_type}")
        response = await process_webhook(request)
        return response
    except Exception as e:
        logger.error(f"Webhook processing failed: {e}", exc_info=True)
        return {"error": str(e)}
