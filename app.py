import re
# ======================================================
# BUILD NESTED DICTIONARY FROM TXT
# ======================================================
def build_nested_dictionary(txt_file_path):
    data = {}
    current_section = "General"
    data[current_section] = {}

    question_lines = []
    answer_lines = []
    reading_answer = False

    with open(txt_file_path, "r", encoding="utf-8") as f:
        lines = [line.rstrip() for line in f.readlines()]

    for line in lines:
        line = line.strip()

        # ---------- SECTION ----------
        section_match = re.match(r"^\d+\.\s+(.*)", line)
        if section_match:
            current_section = section_match.group(1)
            data.setdefault(current_section, {})
            continue

        # ---------- QUESTION START ----------
        if line.startswith("Q."):
            # save previous Q&A
            if question_lines and answer_lines:
                question = " ".join(question_lines).strip()
                answer = " ".join(answer_lines).strip()
                data[current_section][question] = answer

            question_lines = [line.replace("Q.", "").strip()]
            answer_lines = []
            reading_answer = False
            continue

        # ---------- ANSWER START ----------
        if line.startswith("Ans."):
            reading_answer = True
            content = line.replace("Ans.", "").strip()
            if content:
                answer_lines.append(content)
            continue

        # ---------- QUESTION CONTINUATION ----------
        if question_lines and not reading_answer:
            question_lines.append(line)
            continue

        # ---------- ANSWER CONTINUATION ----------
        if reading_answer:
            if line:
                answer_lines.append(line)

    # ---------- SAVE LAST ----------
    if question_lines and answer_lines:
        question = " ".join(question_lines).strip()
        answer = " ".join(answer_lines).strip()
        data[current_section][question] = answer

    return data
# ======================================================
# FAQ QUESTIONS FOR FRONTEND
# ======================================================
def get_faq_questions():
    """
    Return FAQ questions EXCLUDING
    'About Motor Insurance' questions
    """
    questions = []

    for section_name, section_data in NESTED_DATA.items():
        for question in section_data.keys():
            if not isinstance(question, str):
                continue

            question = question.strip()
            questions.append(question)

    return questions

def get_faq_categories():
    categories = []

    for section_name, section_data in NESTED_DATA.items():
        categories.append({
            "title": section_name,
            "questions": list(section_data.keys())
        })

    return categories
# ======================================================
# SINGLE SOURCE OF TRUTH
# ======================================================
NESTED_DATA = build_nested_dictionary("data/motor_insurance.txt")