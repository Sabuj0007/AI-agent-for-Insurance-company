import os
import requests
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import VectorParams, Distance
from typing import List
from difflib import get_close_matches  # <-- for local dictionary fallback

load_dotenv()

# --- CONFIG ---
QDRANT_HOST = os.getenv("QDRANT_HOST", "localhost")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION = os.getenv("COLLECTION", "documents")

EMBED_MODEL_NAME = os.getenv("EMBED_MODEL_NAME", "all-MiniLM-L6-v2")
EMBED_DIM = int(os.getenv("EMBED_DIM", "384"))

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
# allow override but ensure it contains the required openai/v1 prefix
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1")
# If the user set GROQ_BASE_URL without the openai path, fix it:
if GROQ_BASE_URL.rstrip("/").endswith("api.groq.com"):
    GROQ_BASE_URL = GROQ_BASE_URL.rstrip("/") + "/openai/v1"

GROQ_MODEL_NAME = os.getenv("GROQ_MODEL_NAME", "llama-3.3-70b-versatile")
GROQ_TEMPERATURE = float(os.getenv("GROQ_TEMPERATURE", "0.0"))
max_tokens = 1024
GROQ_MAX_TOKENS = int(os.getenv("GROQ_MAX_TOKENS", str(max_tokens)))

RETRIEVE_K = int(os.getenv("RETRIEVE_K", "5"))
FETCH_K = int(os.getenv("FETCH_K", "12"))

# --- LOCAL OFFLINE DICTIONARY (built from motor_insurance.txt) ---
LOCAL_QA = {
    # General motor insurance info
    "what is motor insurance": (
        "Motor insurance protects the vehicle owner against damage to the vehicle and "
        "against Third Party Liability for injury or damage to third party life or property. "
        "Third Party Insurance is mandatory under the Motor Vehicles Act, 1988."
    ),
    "types of motor insurance cover": (
        "There are two main types of motor insurance policies: "
        "(a) Liability Only Policy (statutory, third party only) and "
        "(b) Package Policy, which is Liability Only plus Own Damage (OD) cover for your vehicle."
    ),
    "what motor insurance covers": (
        "Own Damage cover generally includes loss or damage due to: fire, explosion, self-ignition, "
        "lightning, burglary/theft, riot and strike, earthquake, flood, storm, cyclone, tempest, "
        "inundation, hailstorm, frost, accidental external means, malicious acts, terrorism, "
        "damage while in transit by rail/road/inland waterways/lift/elevator/air, and landslide/rock slide."
    ),
    "what motor insurance excludes": (
        "Common exclusions include: driving without a valid driving licence, driving under the influence "
        "of intoxicating liquor or drugs, accidents beyond the geographical limits, use of the vehicle "
        "for unlawful purposes, and purely electrical/mechanical breakdowns."
    ),
    "basis of sum insured": (
        "For Own Damage, the Sum Insured is the Insured’s Declared Value (IDV), based on the manufacturer's "
        "current value less depreciation for age. For Third Party, coverage is provided as per the Motor "
        "Vehicles Act, including compulsory personal accident cover for the owner-driver."
    ),

    # Core FAQs
    "what motor insurance cover should i buy": (
        "Third Party Liability insurance is mandatory for all vehicles on public roads. It covers liability "
        "for injuries and damages to others. It is prudent to buy a Comprehensive/Package policy which covers "
        "both Liability and Own Damage to the insured vehicle."
    ),
    "should i buy comprehensive or liability only": (
        "Liability Only (Act Only) is mandatory but covers only third party liabilities. "
        "A Comprehensive/Package policy covers both third party liabilities and Own Damage and is usually recommended."
    ),
    "how is the premium determined": (
        "Premium depends on many factors including vehicle registration details (engine number, chassis number, "
        "class, cubic capacity, seating capacity), IDV, age of the vehicle, discounts/loading, claims history, "
        "driver details (age, gender, licence validity), and previous insurance history. "
        "Own Damage rates are filed by insurers with IRDA, while Third Party Liability rates are set by IRDA."
    ),
    "what coverage limits meet my needs": (
        "For Own Damage, the Sum Insured is the Insured Declared Value (IDV) and should reflect the current "
        "market value of the vehicle. Third Party injury coverage is unlimited, but third party property damage "
        "is typically covered up to Rs. 7,50,000. You may opt to restrict property damage cover to Rs. 6,000 for a lower premium."
    ),
    "what is the period of the policy": (
        "A motor policy is usually valid for one year and must be renewed on or before the due date. "
        "There is no grace period. Even a one-day lapse requires vehicle inspection. If a comprehensive policy "
        "lapses for more than 90 days, the accumulated No Claim Bonus (NCB) is lost."
    ),
    "what is no claim bonus": (
        "No Claim Bonus (NCB) is a reward for having no claims in the previous policy period. It ranges from 20% "
        "to 50% of the Own Damage premium (not the Liability portion) depending on successive claim-free years. "
        "NCB is given to the insured person, not the vehicle. If a claim is made, NCB is lost in the next period."
    ),
    "will my no claim bonus get migrated if i change my insurance company": (
        "Yes. NCB can be transferred to a new insurer on renewal. You will need proof such as a renewal notice or "
        "a letter from the previous insurer confirming your NCB entitlement or that no claim was lodged."
    ),
    "are there discounts that will lower my premium": (
        "In addition to NCB, discounts may be available for membership of the Automobile Association of India, "
        "certified vintage cars, approved anti-theft devices, concessions for vehicles adapted for the blind or "
        "handicapped, and opting for a voluntary higher deductible. Under Liability Only, a discount is available "
        "if you reduce Third Party Property Damage cover from Rs. 7,50,000 to Rs. 6,000."
    ),
    "is service tax applicable": (
        "Yes, Service Tax (or applicable indirect tax) is charged as per prevailing law."
    ),
    "what is deductible": (
        "Deductible or 'excess' is the portion of a claim that you must bear before the insurer pays the rest. "
        "Standard compulsory excess typically ranges from Rs. 50 for two-wheelers to Rs. 500 for private cars and "
        "commercial vehicles, and may be higher depending on cubic capacity or claims history."
    ),
    "what is the procedure for recording any changes in the policy": (
        "Any change is recorded by an Endorsement. You must submit a written request with supporting proof to the "
        "insurer and obtain the endorsement. Always check the correctness of the endorsement."
    ),
    "if i am using the car in a particular city what premium rate is applied": (
        "For premium rating, the place of registration of the vehicle is considered, not the place of use. "
        "If a vehicle is registered in a metro (Zone A), that rate applies even if it is used elsewhere, and vice versa."
    ),
    "what is a certificate of insurance": (
        "A Certificate of Insurance under the Motor Vehicles Act is issued in Form 51. "
        "It must always be carried in the vehicle, while the full policy document can be kept at home/office."
    ),
    "if i fit cng or lpg kit do i need to inform insurer": (
        "Yes. The RTA must update the Registration Certificate (RC) to reflect the CNG/LPG kit, and the insurer must "
        "be informed. Additional premium is payable on the kit value under both Own Damage and Third Party sections."
    ),
    "what documents must i keep in the vehicle": (
        "You should keep: (1) Certificate of Insurance, (2) copy of Registration Certificate, "
        "(3) valid Pollution Under Control certificate, and (4) copy of the driving licence for the person driving."
    ),
    "can i transfer my insurance to the purchaser of my vehicle": (
        "Yes, the insurance can be transferred to the buyer if the seller informs the insurer in writing and a fresh "
        "proposal form is submitted. A small fee and pro-rata recovery of NCB may apply. In comprehensive/package "
        "policies, transfer must be recorded within 14 days; otherwise Own Damage claims may not be payable."
    ),
    "can i continue insurance in previous owner name": (
        "No. Registration and insurance must always be in the same name with the same address. "
        "If not, claims may not be payable. A fresh proposal form and transfer endorsement are required."
    ),
    "i have lost the insurance policy can i get duplicate": (
        "Yes. Approach the office that issued the policy with a written request. A nominal fee is charged for issuing a duplicate copy."
    ),
    "documents required for motor insurance claim": (
        "Typically: duly filled claim form, RC copy, original repair estimate, repair invoice and payment receipt. "
        "If cashless facility is used, only the repair invoice may be required. FIR may be needed in specific cases. "
        "For theft claims, keys and a non-traceable certificate are also required."
    ),
    "what is idv insured declared value": (
        "IDV (Insured Declared Value) is the value of the vehicle based on the manufacturer’s present value "
        "after depreciation for age. It represents the Sum Insured for Own Damage cover."
    ),
    "what is third party cover": (
        "Third Party cover provides protection against legal liability for injury, death, or property damage to "
        "third parties arising from the use of the vehicle, as required by the Motor Vehicles Act, 1988. "
        "It also includes compulsory personal accident cover for the owner-driver."
    ),
    "policyholder servicing turnaround times": (
        "IRDA has prescribed maximum TATs. Examples: general proposal processing 15 days; obtaining copy of proposal 30 days; "
        "non-claim service requests 10 days; general insurance survey report 30 days; claim settlement 30 days after survey report; "
        "grievance acknowledgement 3 days and resolution 15 days."
    ),
    "how to file grievance with irda": (
        "You should first register your grievance with the insurance company. If unresolved, you can escalate to IRDA through "
        "IGMS (www.igms.irda.gov.in), via email to complaints@irda.gov.in, by letter to the Consumer Affairs Department, "
        "IRDA, or by calling the IRDA Call Centre on toll-free 155255."
    ),
}
LOCAL_QA = {

    # ---- FAQ QUESTIONS FROM FRONTEND ----
    "types of motor insurance cover": (
        "There are two main types of motor insurance policies:\n"
        "1) **Liability Only Policy** – mandatory third party cover\n"
        "2) **Package / Comprehensive Policy** – Liability + Own Damage cover"
    ),

    "how do i file a claim": (
        "To file a motor insurance claim:\n"
        "1. Inform your insurer immediately\n"
        "2. Submit a filled claim form\n"
        "3. Provide RC, DL, and policy copy\n"
        "4. Get a surveyor inspection done\n"
        "5. Repair vehicle and submit bills\n"
        "6. Receive claim settlement"
    ),

    "what is covered in policy": (
        "A comprehensive motor policy covers:\n"
        "- Fire, explosion, theft\n"
        "- Flood, cyclone, storm\n"
        "- Accidental external damage\n"
        "- Riot, strike, terrorism\n"
        "- Damage during transit\n\n"
        "It also offers third-party liability cover."
    ),

    "toll free number and email": (
        "For grievances, you can contact IRDAI:\n"
        "**Toll-free:** 155255\n"
        "**Email:** complaints@irda.gov.in\n"
        "**Portal:** www.igms.irda.gov.in"
    ),

    "check claim status": (
        "You can check claim status by:\n"
        "- Logging into your insurer’s portal\n"
        "- Entering your policy number and claim reference\n"
        "- Or contacting customer support / TPA"
    ),

    "policy period": (
        "A standard motor policy is valid for **1 year**.\n"
        "It must be renewed **on or before the due date**, as there is no grace period."
    ),

    # ---- EXISTING EXTENDED FAQ BELOW ----
    # (keep all your other existing entries here)
}

# --- SMALL TALK RESPONSES (hi, hello, thanks, etc.) ---
SMALL_TALK = {
    "hii": "Hi there! 👋 How can I help you with your motor insurance today?",
    "hello": "Hello! 😊 Ask me anything about your motor insurance policy.",
    "hey": "Hey! What would you like to know about your policy?",
    "how are you": "I’m just code, but I’m running great 😄 How can I help you today?",
    "good morning": "Good morning! 🌅 Do you have any questions about your insurance?",
    "good afternoon": "Good afternoon! ☀️ How can I assist with your policy?",
    "good evening": "Good evening! 🌙 Need help understanding your motor insurance?",
    "thank you": "You’re most welcome! 🙌 If you have more questions, I’m here.",
    "thanks": "Glad I could help! 😊 Anything else about your policy?",
}


def check_small_talk(question: str) -> str | None:
    """
    Check if the user question is basic small talk.
    If yes, return canned reply; otherwise return None.
    """
    q = (question or "").strip().lower()
    if not q:
        return None

    # simple containment match: if key is part of user text
    for key, reply in SMALL_TALK.items():
        if key in q:
            return reply

    return None


def local_dictionary_answer(question: str) -> str:
    """
    Offline QA fallback using LOCAL_QA.
    - Fuzzy match the user question to keys in LOCAL_QA.
    - If nothing close, try simple substring match.
    - If still nothing, return a generic offline message.
    """
    q = (question or "").strip().lower()
    if not q:
        return "Please provide a question so I can look it up in the local motor insurance FAQs."

    if not LOCAL_QA:
        return "I am currently offline and no local FAQ answers are configured."

    keys = list(LOCAL_QA.keys())

    # Fuzzy match (best effort)
    matches = get_close_matches(q, keys, n=1, cutoff=0.6)
    if matches:
        return LOCAL_QA[matches[0]]

    # Substring match as backup
    for k, v in LOCAL_QA.items():
        if k in q:
            return v

    # Final generic fallback
    return (
        "I am unable to reach the main AI service right now, and I do not have an exact "
        "offline answer stored for this question in the motor insurance FAQs."
    )


# --- APP ---
app = FastAPI()
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"]
)

# --- Embedder ---
try:
    embedder = SentenceTransformer(EMBED_MODEL_NAME)
    embed_error = None
except Exception as e:
    embedder = None
    embed_error = str(e)


def embed_texts(texts):
    if embedder is None:
        raise RuntimeError(f"Embedder not loaded: {embed_error}")
    if isinstance(texts, str):
        texts = [texts]
    vecs = embedder.encode(texts, show_progress_bar=False)
    return vecs.tolist() if hasattr(vecs, "tolist") else vecs


# --- Qdrant client ---
qdrant_error = None
qdrant = None
try:
    qdrant = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
    try:
        qdrant.get_collection(COLLECTION)
    except Exception:
        qdrant.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=EMBED_DIM, distance=Distance.COSINE),
        )
except Exception as e:
    qdrant = None
    qdrant_error = str(e)


# --- FIXED ask_groq (enforces correct URL + logging) ---
def ask_groq(
    prompt: str,
    model: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
) -> str:
    """
    Sends the prompt to Groq chat completions. This function enforces the
    correct /openai/v1 prefix on the base URL and logs the returned payload
    for debugging.
    """
    if not GROQ_API_KEY:
        return "Groq API key missing. Set GROQ_API_KEY in environment."

    model = model or GROQ_MODEL_NAME
    temperature = GROQ_TEMPERATURE if temperature is None else temperature
    max_tokens = GROQ_MAX_TOKENS if max_tokens is None else max_tokens

    # ensure base URL ends with /openai/v1 (defensive)
    base = GROQ_BASE_URL.rstrip("/")
    if not base.endswith("/openai/v1"):
        base = base.rstrip("/") + "/openai/v1"

    url = f"{base}/chat/completions"

    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    print("-> Groq request URL:", url)
    print("-> Groq request model:", model)
    print("-> Groq request body preview:", repr(prompt)[:300])

    try:
        resp = requests.post(url, headers=headers, json=body, timeout=60)
    except requests.RequestException as e:
        return f"Groq request failed: {e}"

    print("<- Groq status:", resp.status_code)
    print("<- Groq response body:", resp.text[:2000])  # limit log size

    try:
        data = resp.json()
    except Exception:
        return f"Groq non-JSON response: HTTP {resp.status_code} - {resp.text}"

    if resp.status_code != 200:
        err = data.get("error", data)
        return f"Groq API {resp.status_code}: {err}"

    try:
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        return f"Groq response parse error: {e} - {data}"


# --- Pydantic models + endpoints ---
class AskRequest(BaseModel):
    question: str


class ChunkOut(BaseModel):
    text: str
    source: str | None = None
    score: float | None = None


class AskResponse(BaseModel):
    answer: str
    chunks: List[ChunkOut]


@app.get("/status")
def status():
    return {
        "qdrant_host": QDRANT_HOST if qdrant else "ERROR",
        "qdrant_port": QDRANT_PORT,
        "collection": COLLECTION,
        "embed_model": EMBED_MODEL_NAME,
        "groq_key_loaded": bool(GROQ_API_KEY),
        "embed_error": embed_error,
        "qdrant_error": qdrant_error,
        "retrieve_k": RETRIEVE_K,
        "fetch_k": FETCH_K,
        "groq_model": GROQ_MODEL_NAME,
        "groq_base_url_in_use": GROQ_BASE_URL,
    }


@app.post("/ask", response_model=AskResponse)
def api_ask(req: AskRequest):
    query = (req.question or "").strip()
    if not query:
        return AskResponse(answer="Please provide a question.", chunks=[])

    # --- 1) SMALL TALK SHORT-CIRCUIT ---
    st_reply = check_small_talk(query)
    if st_reply:
        # For hi/hello/thanks type messages, skip Qdrant + Groq completely
        return AskResponse(answer=st_reply, chunks=[])

    # --- 2) If Qdrant or embedder is not ready -> fallback to local dictionary ---
    if not qdrant or embedder is None:
        offline_answer = local_dictionary_answer(query)
        return AskResponse(answer=offline_answer, chunks=[])

    try:
        # Embedding with fallback
        try:
            qvec = embed_texts(query)[0]
        except Exception as e:
            print("Embedding error:", e)
            offline_answer = local_dictionary_answer(query)
            return AskResponse(answer=offline_answer, chunks=[])

        # Qdrant search with fallback
        try:
            search = qdrant.query_points(
                collection_name=COLLECTION,
                query=qvec,
                limit=FETCH_K,
                with_payload=True,
            )
            matches = search.points if search else []
        except Exception as e:
            print("Qdrant search error:", e)
            offline_answer = local_dictionary_answer(query)
            return AskResponse(answer=offline_answer, chunks=[])

        if not matches:
            # No vector matches -> fallback to offline FAQ
            offline_answer = local_dictionary_answer(query)
            return AskResponse(answer=offline_answer, chunks=[])

        top_matches = matches[:RETRIEVE_K]
        context_parts: List[str] = []
        chunks_out: List[ChunkOut] = []

        for m in top_matches:
            payload = getattr(m, "payload", None) or (m.payload if hasattr(m, "payload") else {})
            text = payload.get("text", "") if isinstance(payload, dict) else ""
            src = payload.get("source", None) if isinstance(payload, dict) else None
            score = getattr(m, "score", None)
            if text:
                context_parts.append(text)
            chunks_out.append(ChunkOut(text=text, source=src, score=score))

        context = "\n\n".join([p for p in context_parts if p])

        prompt = f"""
use your natural language processing skills to answer the question based on the provided context from the policy document.
Use a professional tone.

Context:
{context}

Question:
{query}

Use clear and concise language in your answer.
""".strip()

        answer = ask_groq(
            prompt=prompt,
            model=GROQ_MODEL_NAME,
            temperature=GROQ_TEMPERATURE,
            max_tokens=GROQ_MAX_TOKENS,
        )

        # If Groq response looks like an error -> fallback to local
        error_signals = [
            "groq api",
            "groq request failed",
            "groq non-json response",
            "groq response parse error",
            "groq api key missing",
        ]
        lower_answer = (answer or "").lower()
        if any(sig in lower_answer for sig in error_signals):
            print("Groq failed, using local dictionary fallback.")
            offline_answer = local_dictionary_answer(query)
            return AskResponse(answer=offline_answer, chunks=chunks_out)

        return AskResponse(answer=answer, chunks=chunks_out)

    except Exception as e:
        # Last-resort fallback
        print("Unexpected error in /ask:", e)
        offline_answer = local_dictionary_answer(query)
        return AskResponse(answer=offline_answer, chunks=[])
