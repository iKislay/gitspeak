import tiktoken
from typing import List, Dict, Any

class Chunker:
    """
    Chunks fetched items for embedding logic.
    """
    def __init__(self, model: str = "cl100k_base", threshold_tokens: int = 400):
        self.encoding = tiktoken.get_encoding(model)
        self.threshold = threshold_tokens

    def _split_into_paragraphs(self, text: str) -> List[str]:
        return [p.strip() for p in text.split('\n\n') if p.strip()]

    def _split_into_sentences(self, text: str) -> List[str]:
        # Simple sentence splitter based on punctuation
        import re
        sentences = re.split(r'(?<=[.!?]) +', text)
        return [s.strip() for s in sentences if s.strip()]

    def _chunk_text(self, text: str) -> List[str]:
        """Split text while trying to stay under threshold natively without breaking sentences"""
        tokens = len(self.encoding.encode(text))
        if tokens <= self.threshold:
            return [text]

        chunks = []
        current_chunk = []
        current_length = 0

        paragraphs = self._split_into_paragraphs(text)
        for paragraph in paragraphs:
            para_tokens = len(self.encoding.encode(paragraph))
            
            # If paragraph itself is too large, split by sentences
            if para_tokens > self.threshold:
                sentences = self._split_into_sentences(paragraph)
                for sentence in sentences:
                    sentence_tokens = len(self.encoding.encode(sentence))
                    if current_length + sentence_tokens > self.threshold and current_chunk:
                        chunks.append(" ".join(current_chunk))
                        current_chunk = []
                        current_length = 0
                    current_chunk.append(sentence)
                    current_length += sentence_tokens
            else:
                if current_length + para_tokens > self.threshold and current_chunk:
                    chunks.append("\n\n".join(current_chunk))
                    current_chunk = []
                    current_length = 0
                current_chunk.append(paragraph)
                current_length += para_tokens

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        return chunks

    def process(self, items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        processed_chunks = []
        for item in items:
            text = item.get("content", "")
            raw_chunks = self._chunk_text(text)
            
            # Carry metadata forward
            for idx, raw_chunk in enumerate(raw_chunks):
                chunk_dict = item.copy()  # copies type, id, title, author, date, url, repo
                chunk_dict["chunk_index"] = idx
                chunk_dict["chunk_total"] = len(raw_chunks)
                chunk_dict["text"] = raw_chunk
                
                # Removing the original full content to avoid huge payloads if not needed
                # However, Qdrant payload will hold the rest.
                if "content" in chunk_dict:
                    del chunk_dict["content"]
                    
                processed_chunks.append(chunk_dict)
                
        return processed_chunks
