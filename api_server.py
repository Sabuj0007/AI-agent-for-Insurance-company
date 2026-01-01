import os
import re
import numpy as np
from typing import List, Tuple
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import requests
from qdrant_client import QdrantClient
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from app import NESTED_DATA, get_faq_questions

# =========================
# LOAD ENV
# =========================
load_dotenv()

# Embeddings
EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")

# FAQ retrieval
FAQ_RETRIEVAL_K = int(os.getenv("FAQ_RETRIEVAL_K", 3))
FAQ_SIM_THRESHOLD = float(os.getenv("FAQ_SIM_THRESHOLD", 0.60))

# Qdrant
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", 6333))
QDRANT_COLLECTION = "documents"

# Groq
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not set")
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com")
GROQ_MODEL = "llama-3.3-70b-versatile"
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", 1024))


# =========================
# INIT CLIENTS
# =========================
embedder = SentenceTransformer(EMBED_MODEL_NAME)
qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# =========================
# FASTAPI APP
# =========================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5500",
        "http://localhost:3000",
        "http://localhost:8000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================
# MODELS
# =========================
class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str
    source: str
# =========================
# PROMPT (RAG)
# =========================
# =========================
# MASTER MOTOR INSURANCE PROMPT
# (IRDA Handbook–Bound | Zero Hallucination)
# =========================
SYSTEM_PROMPT = """
You are a Senior Motor Insurance Advisor with extensive experience in customer servicing and claims handling.

Your responsibility is to answer motor insurance questions accurately, clearly, and professionally,
using ONLY the information available in the provided Motor Insurance Handbook.

You must behave like a real insurance advisor speaking to a policyholder.

STRICT GOVERNING RULES (NON-NEGOTIABLE):
1. Use ONLY information explicitly stated in the document.
2. Do NOT add external knowledge, assumptions, or interpretations.
3. Do NOT introduce terms, limits, clauses, or benefits unless they appear in the document.
4. Do NOT reference any law, rule, or authority unless named in the document.
5. Do NOT invent examples, scenarios, or numbers.
6. Do NOT use meta words such as:
   - context
   - source
   - document says
   - handbook states
7. Do NOT use filler phrases such as:
   - "It depends"
   - "Generally speaking"
   - "In most cases"

MANDATORY FALLBACK RULE:
If the document does NOT contain sufficient information to answer the question,
respond EXACTLY with the following text and nothing else:

"Based on the available information, I am unable to provide a specific answer.
Please contact your insurance provider for further assistance."

ANSWER STRUCTURE (ONLY IF ANSWER IS AVAILABLE):
1. Start with a simple explanation in plain language.
2. Provide a structured breakdown using bullet points or numbered lists.
3. Highlight key terms using **bold** ONLY if those terms exist in the document.

TONE & STYLE:
- Professional
- Calm
- Confident
- Customer-friendly
- Neutral and advisory

GREETING & SMALL-TALK RULE:
- If the user message is a greeting or casual phrase, respond briefly and politely.
- Do NOT provide insurance information unless explicitly asked.
- Invite the user to ask a motor insurance question in one short sentence.

PROACTIVE CONTENT RESTRICTION:
- Do NOT suggest topics or actions unless explicitly asked.
- Do NOT introduce guidance questions.
- Do NOT jump to advanced topics unless requested.

CONTEXT:
{context}

USER QUESTION:
{question}
"""
# ========================
# UTILS
# =========================
def normalize(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return re.sub(r"\s+", " ", text)

# =========================
# FAQ RETRIEVAL-K
# =========================
def build_faq_pairs() -> List[Tuple[str, str]]:
    pairs = []
    for _, items in NESTED_DATA.items():
        for q, a in items.items():
            if isinstance(a, str):
                pairs.append((q, a))
    return pairs

FAQ_PAIRS = build_faq_pairs()
FAQ_QUESTIONS = [q for q, _ in FAQ_PAIRS]
FAQ_EMBEDDINGS = embedder.encode(FAQ_QUESTIONS)

def get_exact_faq_answer(question: str) -> str | None:
    """
    Fetch answer ONLY if question exactly exists
    in NESTED_DATA (single source of truth).
    """
    q_norm = normalize(question)

    for section, qa_map in NESTED_DATA.items():
        for faq_q, faq_a in qa_map.items():
            if normalize(faq_q) == q_norm:
                return faq_a

    return None

# =========================
# QDRANT RETRIEVAL
# =========================
def retrieve_from_qdrant(question: str, k: int = 4) -> List[str]:
    vector = embedder.encode(question).tolist()

    result = qdrant.query_points(
        collection_name=QDRANT_COLLECTION,
        query=vector,
        limit=k,
        with_payload=True,
    )

    return [
        point.payload.get("text", "")
        for point in result.points
        if point.payload and "text" in point.payload
    ]

# =========================
# GROQ LLM (RAG)
# =========================
def ask_groq_llm(question: str, context_chunks: List[str]) -> str:
    context = "\n\n".join(context_chunks)

    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Context:\n{context}\n\nQuestion:\n{question}",
            },
        ],
        "temperature": 0.2,
        "max_tokens": GROQ_MAX_TOKENS,
    }

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }

    res = requests.post(
        f"{GROQ_BASE_URL}/openai/v1/chat/completions",
        headers=headers,
        json=payload,
        timeout=30,
    )
    res.raise_for_status()
    return res.json()["choices"][0]["message"]["content"]

# =========================
# ROUTE
# =========================
@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):

# 2️⃣ EXACT FAQ from nested data (SAFE & CORRECT)
    faq_answer = get_exact_faq_answer(req.question)
    if faq_answer:
        return AskResponse(answer=faq_answer, source="faq-exact")


    # 3️⃣ Qdrant + Groq
    chunks = retrieve_from_qdrant(req.question)
    llm_answer = ask_groq_llm(req.question, chunks)

    return AskResponse(answer=llm_answer, source="qdrant+groq")

@app.get("/status")
def status():
    return {
        "faq_count": len(FAQ_PAIRS),
        "qdrant_collection": QDRANT_COLLECTION,
        "qdrant_points": "412",
        "llm_model": GROQ_MODEL,
    }
@app.get("/faqs")
def faqs():
    return {
        "faqs": get_faq_questions()
    }
