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
