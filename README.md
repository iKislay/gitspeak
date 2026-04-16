# Voice Codebase Oracle

A voice-first AI agent that allows developers to ask questions about any GitHub repository out loud and receive a spoken, context-aware answer with source attribution. Built with VAPI, Qdrant, Ollama Cloud, and Gemini.

## Architecture

```
  User Voice                Text Query                 Semantic Search
  -------->   VAPI Webhook   -------->    FastAPI APP    -------->    Qdrant DB
              (Speech to Text)                                        (Vector DB)
                                                                      (Gemini Embeddings)
  <--------                  <--------                   <--------
  Spoken Answer Formatted Response Context (PRs, Commits, README)
               + Ollama Cloud (Llama 3)
```

## Detailed Setup Instructions

1. **Clone the repository.**

2. **Set up Virtual Environment:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Create a `.env` file in the root directory with the following variables:
   ```env
   GITHUB_TOKEN=your_github_token
   QDRANT_URL=your_qdrant_cloud_url
   QDRANT_API_KEY=your_qdrant_api_key
   COLLECTION_NAME=codebase_oracle
   OLLAMA_API_KEY=your_ollama_cloud_api_key
   OLLAMA_BASE_URL=https://api.ollama.com/v1
   OLLAMA_MODEL=llama3
   GOOGLE_API_KEY=your_gemini_api_key
   VAPI_SECRET=your_vapi_webhook_secret
   ```
   *Note: Gemini (`GOOGLE_API_KEY`) is used for generating high-quality embeddings, while Ollama Cloud is used for text generation.*

5. **Index a Repository:**
   Run the demo ingestion script to index a small repository (e.g., `octocat/Spoon-Knife`):
   ```bash
   python3 demo/ingest_demo_repo.py
   ```
   To index a different repo, you can use the `/ingest` endpoint once the server is running.

6. **Start the FastAPI server:**
   ```bash
   uvicorn server.main:app --host 0.0.0.0 --port 8000
   ```

## VAPI Configuration

1. Create an account at [vapi.ai](https://vapi.ai)
2. Create a new Assistant.
3. Under the webhook settings, set your Server URL to `https://<YOUR_TUNNEL>/webhook` (use Ngrok to tunnel your local port `8000`).
4. Add a custom Server Tool called `search_codebase` (Description: "Search the indexed codebase to answer developer questions").
   - Parameters:
     - `query` (string): The question about the codebase.
     - `repo` (string): The repository slug (owner/repo).
5. Provide your `VAPI_SECRET` in `.env` to ensure requests are verified.

## Example Questions to Ask

Once connected, ask the assistant:
- "What is the purpose of the Spoon-Knife repository?"
- "Who are the main contributors to this project?"
- "What's in the README of this repo?"

## Troubleshooting

- **Vector Dimension Error:** If you see an error about expected dim 768 vs 3072, ensure you are using `models/gemini-embedding-001` which produces 3072-dimensional vectors. The project is configured to handle this.
- **404 Model Not Found:** Ensure your `GOOGLE_API_KEY` is valid and has access to the Gemini Embedding models.
