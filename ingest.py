# ingest.py
from pathlib import Path
import os
import uuid
import socket
from typing import List

from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance, PointStruct
from sentence_transformers import SentenceTransformer
import httpcore

# CONFIG (can be overridden via env)
DATA_FILE = Path(os.getenv("DATA_FILE", "data/motor_insurance.txt"))
COLLECTION_NAME = os.getenv("COLLECTION_NAME", "documents")
EMBED_MODEL_NAME = os.getenv(
    "EMBED_MODEL_NAME", "all-MiniLM-L6-v2"
)
QDRANT_HOST = os.getenv("QDRANT_HOST", "qdrant")  # default service name for docker-compose
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
BATCH_SIZE = int(os.getenv("BATCH_SIZE", 256))


def load_sentences(path: Path) -> List[str]:
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {path}")
    text = path.read_text(encoding="utf-8")
    sentences = [line.strip() for line in text.splitlines() if line.strip()]
    return sentences


def ensure_collection(client: QdrantClient, name: str, dim: int):
    try:
        cols = client.get_collections().collections
        exists = any(c.name == name for c in cols)
    except Exception:
        exists = False

    if exists:
        print(f"[qdrant] Collection '{name}' already exists")
        return

    print(f"[qdrant] Creating collection '{name}' (dim={dim}) ...")
    client.create_collection(
        collection_name=name,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )
    # verify creation
    cols_after = client.get_collections().collections
    if not any(c.name == name for c in cols_after):
        raise RuntimeError(f"Failed to create collection '{name}'")
    print(f"[qdrant] Created collection '{name}'")


def upsert_in_batches(client: QdrantClient, name: str, points: List[PointStruct]):
    total = len(points)
    print(f"[qdrant] Upserting {total} points in batches of {BATCH_SIZE} ...")
    for i in range(0, total, BATCH_SIZE):
        batch = points[i : i + BATCH_SIZE]
        client.upsert(collection_name=name, points=batch)
        print(f"  upserted {i + len(batch)}/{total}")


def try_connect(host: str, port: int):
    """Attempt to instantiate a QdrantClient and perform a lightweight ping to confirm connectivity."""
    client = QdrantClient(host=host, port=port, prefer_grpc=False)
    # call a simple endpoint to validate connection
    try:
        client.get_collections()
        return client
    except (httpcore.ConnectError, socket.gaierror, ConnectionRefusedError) as e:
        raise e
    except Exception:
        # other exceptions — still treat as connection failure for resolution fallback
        raise


def get_working_client(preferred_host: str, port: int):
    # Try in this order: configured host -> localhost -> 127.0.0.1
    tried = []
    for candidate in [preferred_host, "localhost", "127.0.0.1"]:
        if candidate in tried:
            continue
        tried.append(candidate)
        print(f"[qdrant] Trying to connect to {candidate}:{port} ...")
        try:
            client = try_connect(candidate, port)
            print(f"[qdrant] Connected to {candidate}:{port}")
            return client
        except Exception as e:
            print(f"[qdrant] Could not connect to {candidate}:{port} — {e}")
    # none worked, raise final helpful error
    raise ConnectionError(
        f"Failed to connect to Qdrant on any host (tried: {', '.join(tried)}). "
        "If you're running locally, make sure Qdrant is running and listening on port 6333. "
        "If using docker-compose, run ingest.py inside the same compose network or set QDRANT_HOST=localhost when running on host."
    )


def main():
    print(f"[data] Loading text from {DATA_FILE} ...")
    sentences = load_sentences(DATA_FILE)
    if not sentences:
        print("[data] No sentences found — exiting")
        return
    print(f"[data] Loaded {len(sentences)} lines")

    print(f"[embed] Loading model: {EMBED_MODEL_NAME} ...")
    model = SentenceTransformer(EMBED_MODEL_NAME)
    vectors = model.encode(sentences)
    dim = vectors.shape[1] if hasattr(vectors, "shape") else len(vectors[0])
    print(f"[embed] Got vectors with dim={dim}")

    print(f"[qdrant] Attempting to connect (preferred host from env: '{QDRANT_HOST}') ...")
    client = get_working_client(QDRANT_HOST, QDRANT_PORT)

    # ensure collection exists
    ensure_collection(client, COLLECTION_NAME, dim)

    # prepare PointStructs
    print("[qdrant] Preparing points ...")
    points = [
        PointStruct(id=str(uuid.uuid4()), vector=vectors[i].tolist(), payload={"text": sentences[i], "source": str(DATA_FILE)})
        for i in range(len(sentences))
    ]

    # upsert in batches
    upsert_in_batches(client, COLLECTION_NAME, points)

    print("✅ Successfully stored text into Qdrant!")


if __name__ == "__main__":
    main()
