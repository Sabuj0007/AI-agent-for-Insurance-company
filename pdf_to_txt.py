import os, re, unicodedata
import pdfplumber
from collections import defaultdict

pdf_path = r"C:\\Users\\SABUJ KARMAKAR\\QA\\Motor_Insurance.pdf".strip()
base, _ = os.path.splitext(pdf_path)
txt_path = base + ".txt"

# ---------- TUNABLES ----------
GUTTER_PX       = 10   # gap near the red divider
LINE_TOL        = 3    # line grouping tolerance (px)
NOISE_THRESHOLD = 0.55 # min (letters+digits)/len(line) to keep a line
MIN_LINE_LEN    = 4    # drop tiny lines unless meaningful
CONFUSABLE_MAX  = 0.60 # if >60% of chars are confusables -> drop the line
# ------------------------------

TRANSLATE_TABLE = str.maketrans({
    "“":"\"", "”":"\"", "‘":"'", "’":"'",
    "–":"-", "—":"-", "•":"*", "●":"*",
    "…":"...", "₹":" Rs ", "™":"", "®":"", "©":""
})

BOX_DRAWING_RX = re.compile(r"[┌┐└┘├┤┬┴┼─━│┃┆┇┊┋╭╮╯╰═║]+")
DIVIDER_RX     = re.compile(r"[|_¯=]+")
MULTI_SPACE_RX = re.compile(r"[ \t]{2,}")
WEIRD_RX       = re.compile(r"[^A-Za-z0-9\s\.,;:'\"()\[\]/&%@$#\+\-\?!]")

URL_EMAIL_RX   = re.compile(r"(www\.|https?://|@[A-Za-z0-9_.-]+|\.[A-Za-z]{2,})")

# characters that often form junk: l/I/1/!/|/`/'/~ etc.
CONFUSABLE_CHARS = set("lI1!|`'~^:;[]{}<>°º·•—–-_=+\\")
VOWELS_RX = re.compile(r"[AEIOUaeiou]")

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKC", s).translate(TRANSLATE_TABLE)
    s = BOX_DRAWING_RX.sub(" ", s)
    s = DIVIDER_RX.sub(" ", s)
    s = WEIRD_RX.sub(" ", s)
    s = re.sub(r"([.\-_,;:'\"!?/()])\1{2,}", r"\1\1", s)
    s = MULTI_SPACE_RX.sub(" ", s)
    return s.strip()

def confusable_ratio(s: str) -> float:
    if not s:
        return 1.0
    total = sum(1 for ch in s if not ch.isspace())
    if total == 0:
        return 1.0
    conf = sum(1 for ch in s if ch in CONFUSABLE_CHARS)
    return conf / total

def looks_acronym(line: str) -> bool:
    # keep legit acronyms like "IRDA", "RTO", etc.
    return bool(re.fullmatch(r"[A-Z]{2,}(?:\s+[A-Z]{2,})*", line))

def is_meaningful(line: str) -> bool:
    if not line:
        return False
    if URL_EMAIL_RX.search(line):
        return True
    # Drop lines dominated by confusable characters (your highlighted noise)
    if confusable_ratio(line) > CONFUSABLE_MAX:
        return False
    # Keep phone-like lines
    digits = sum(ch.isdigit() for ch in line)
    if digits >= 4:
        return True
    # Keep acronyms (IRDA, RTO, etc.)
    if looks_acronym(line):
        return True
    # Require some vowels to avoid random consonant soup, but allow one-word titles
    letters = sum(ch.isalpha() for ch in line)
    if letters >= 3 and not VOWELS_RX.search(line):
        return False
    alnum = sum(ch.isalnum() for ch in line)
    if len(line) < MIN_LINE_LEN:
        return False
    return (alnum / max(1, len(line))) >= NOISE_THRESHOLD

def words_to_text(words, line_tol=LINE_TOL):
    if not words: return ""
    buckets = defaultdict(list)
    for w in words:
        t = (w.get("text") or "").strip()
        if not t: continue
        buckets[int(round(w["top"] / line_tol))].append(w)

    lines = []
    for b in sorted(buckets.keys()):
        line_words = sorted(buckets[b], key=lambda w: w["x0"])
        raw = " ".join((w["text"] or "").strip() for w in line_words).strip()
        cln = normalize_text(raw)
        if cln and is_meaningful(cln):
            lines.append(cln)

    text = "\n".join(lines)
    text = re.sub(r"-\n(?=[a-z])", "", text)  # join hyphenated words
    return text

def extract_half(page, bbox):
    half = page.crop(bbox)
    words = half.extract_words(x_tolerance=1, y_tolerance=1, keep_blank_chars=False, use_text_flow=False)
    return words_to_text(words)

all_pages_text = []

try:
    with pdfplumber.open(pdf_path) as pdf:
        for i, page in enumerate(pdf.pages, start=1):
            W, H = page.width, page.height
            mid = W / 2
            left_bbox  = (0, 0, max(0, mid - GUTTER_PX), H)
            right_bbox = (min(W, mid + GUTTER_PX), 0, W, H)

            left_text  = extract_half(page, left_bbox)
            right_text = extract_half(page, right_bbox)

            combined = "\n\n".join([t for t in (left_text, right_text) if t.strip()])
            if combined:
                all_pages_text.append(combined)

    final_text = ("\n\n" + ("-" * 60) + "\n\n").join(all_pages_text)
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(final_text)

    print("✅ Clean, ordered text saved.")
    print(f"📁 {txt_path}")

except Exception as e:
    print("❌ Error:", e)
