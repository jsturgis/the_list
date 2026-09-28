from __future__ import annotations
"""Ollama embedding client."""
import httpx
import numpy as np

from app.config import settings


async def embed(text: str) -> np.ndarray:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embedding_model, "input": text},
            timeout=60.0,
        )
        response.raise_for_status()
        return np.array(response.json()["embeddings"][0], dtype=np.float32)


async def embed_batch(texts: list[str]) -> list[np.ndarray]:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.ollama_embedding_model, "input": texts},
            timeout=120.0,
        )
        response.raise_for_status()
        return [np.array(e, dtype=np.float32) for e in response.json()["embeddings"]]
