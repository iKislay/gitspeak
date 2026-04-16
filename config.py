import os
from dotenv import load_dotenv

load_dotenv()

# GitHub Configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

# Qdrant Configuration
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "local_no_api_key")
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "codebase_oracle")

# Ollama Cloud Configuration (OpenAI-compatible)
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL") # e.g., https://api.ollama.com/v1
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3")

# Gemini Configuration (for embeddings)
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_EMBED_MODEL = "models/gemini-embedding-001"

# Fallbacks for specific logic
LLM_MODEL = OLLAMA_MODEL
EMBEDDING_MODEL = GEMINI_EMBED_MODEL

# VAPI Configuration
VAPI_SECRET = os.getenv("VAPI_SECRET")

# Backend public URL (used to self-reference in Vapi tool config)
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

# Deep Code Ingestion Configuration
INGEST_SOURCE_FILES = os.getenv("INGEST_SOURCE_FILES", "true").lower() == "true"
MAX_FILE_SIZE_BYTES = int(os.getenv("MAX_FILE_SIZE_BYTES", "51200"))  # 50 KB default
MAX_SOURCE_FILES = int(os.getenv("MAX_SOURCE_FILES", "200"))  # cap for large repos
INGESTED_EXTENSIONS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".java", ".rs",
    ".rb", ".cs", ".cpp", ".c", ".h", ".swift", ".kt",
    ".md", ".yaml", ".yml", ".json", ".toml", ".sh",
}
SKIP_PATH_PATTERNS = {
    "node_modules", "__pycache__", ".git", "dist", "build",
    "vendor", ".venv", "venv", "env", ".mypy_cache", ".pytest_cache",
    "coverage", ".next", "target", "out", ".tox",
}
