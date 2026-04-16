# Voice Codebase Oracle

A voice-first AI agent that allows developers to ask questions about any GitHub repository out loud and receive a spoken, context-aware answer with source attribution. Built with VAPI, Qdrant, and OpenAI.

## Architecture

```
  User Voice                Text Query                 Semantic Search
  -------->   VAPI Webhook   -------->    FastAPI APP    -------->    Qdrant DB
              (Speech to Text)                                        (Vector DB)
  <--------                  <--------                   <--------
  Spoken Answer Formatted Response Context (PRs, Commits, README)
               + OpenAI GPT-4o
```

## Setup Instructions

1. Clone this repository.
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy the `.env.example` file to create your own configuration:
   ```bash
   cp .env.example .env
   ```
   Provide valid keys for `GITHUB_TOKEN`, `OPENAI_API_KEY`, Qdrant specifics, and `VAPI_SECRET`.
4. Index a demo repository:
   ```bash
   python demo/ingest_demo_repo.py
   ```
5. Start the FastAPI server:
   ```bash
   uvicorn server.main:app --port 8000
   ```

## VAPI Configuration

1. Create an account at [vapi.ai](https://vapi.ai)
2. Create a new Assistant.
3. Under the webhook settings, set your Server URL to `https://<YOUR_TUNNEL>/webhook` (use Ngrok to tunnel your local port `8000`).
4. Add a custom Server Tool called `search_codebase` (Description: "Search the indexed codebase to answer developer questions").
5. Provide your `VAPI_SECRET` in `.env` to ensure requests are verified.

## Example Questions to Ask

Once connected, ask the assistant:
- "Why did this project move to hooks?"
- "Who introduced the fiber reconciler?"
- "What changed in March 2023?"
- "What does the packages directory contain?"

## Known Limitations

- In the current MVP, fetching PRs/Commits operates without advanced chunk summarization. Extremely large commits are handled naively using standard token splitting.
- Only closed/merged PRs and Commits are tracked; Open PRs are not included yet.
- In-memory conversation state tracking is used only locally for the MVP scope (no persistent redis cache).
