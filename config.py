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
OLLAMA_EMBED_MODEL = os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")

# Fallbacks for specific logic
LLM_MODEL = OLLAMA_MODEL
EMBEDDING_MODEL = OLLAMA_EMBED_MODEL

# VAPI Configuration
VAPI_SECRET = os.getenv("VAPI_SECRET")
