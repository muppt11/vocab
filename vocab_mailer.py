from dotenv import load_dotenv
import os
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import json
import random
import requests
from nltk.corpus import wordnet
from bs4 import BeautifulSoup
import re

# ------------------ ENV ------------------
load_dotenv()
SENDER_EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECIPIENTS = [e.strip() for e in os.getenv("RECIPIENTS", SENDER_EMAIL).split(",") if e.strip()]

REQ_TIMEOUT = 5
REQ_HEADERS = {"User-Agent": "VocabMailer/1.0 (https://github.com/muppt11/vocab)"}

# ------------------ SENT WORDS LOG ------------------
def get_sent_words():
    try:
        with open("sent_words.json", "r") as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_sent_word(word):
    sent = get_sent_words()
    sent.add(word)
    with open("sent_words.json", "w") as f:
        json.dump(list(sent), f, indent=2)

# ------------------ RANDOM WORD SOURCE ------------------
def get_random_words_from_datamuse(limit=200):
    """
    Fetch random words filtered by both topic and random letter pattern.
    Ensures variety while keeping a real category label.
    Returns (word_list, topic).
    """
    topics = [
        "nature", "emotion", "society", "literature", "science",
        "technology", "philosophy", "art", "music", "education", "psychology"
    ]
    topic = random.choice(topics)
    letters = "abcdefghijklmnopqrstuvwxyz"
    letter = random.choice(letters)

    all_words = []

    # Combined topic + pattern query
    url = f"https://api.datamuse.com/words?topics={topic}&sp={letter}*&max={limit}"


    try:
        r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            data = r.json()
            all_words = [d.get("word", "") for d in data if d.get("word", "").isalpha()]
    except requests.RequestException:
        pass

    # fallback if topic query returns too few words
    if len(all_words) < 20:
        try:
            url = f"https://api.datamuse.com/words?topics={topic}&max={limit}"
            r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
            if r.status_code == 200:
                data = r.json()
                all_words = [d.get("word", "") for d in data if d.get("word", "").isalpha()]
                print(f"Fallback: topic-only list (topic '{topic}') used.")
        except requests.RequestException:
            pass

    # final fallback if everything else fails
    if len(all_words) < 20:
        try:
            url = f"https://api.datamuse.com/words?sp=*&max={limit}"
            r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
            if r.status_code == 200:
                data = r.json()
                all_words = [d.get("word", "") for d in data if d.get("word", "").isalpha()]
                topic = "general vocabulary"
                print("Fallback: generic list used.")
        except requests.RequestException:
            pass

    random.shuffle(all_words)
    print(f"Fetched {len(all_words)} words for topic '{topic}' (letter filter '{letter}').")
    return all_words, topic


# ------------------ SYNONYMS ------------------
def get_synonyms_from_datamuse(word):
    try:
        url = f"https://api.datamuse.com/words?ml={word}"
        r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            data = r.json()
            syns = [item.get("word", "") for item in data[:10] if item.get("word")]
            if syns:
                return syns
    except requests.RequestException:
        pass
    syns = [lemma.name().replace('_', ' ') for syn in wordnet.synsets(word) for lemma in syn.lemmas()]
    return sorted(set(syns))[:10]

# ------------------ CONTEXT SCRAPERS ------------------
def get_wiktionary_context(word):
    try:
        url = f"https://en.wiktionary.org/wiki/{word}"
        r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            definition = soup.select_one("ol li")
            if definition:
                return definition.get_text(" ", strip=True)
    except requests.RequestException:
        pass
    return None

def get_wikipedia_context(word):
    try:
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{word}"
        r = requests.get(api_url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract")
            if extract and "may refer to" not in extract.lower():
                sentences = extract.split(". ")
                short_text = ". ".join(sentences[:3]).strip()
                return short_text if short_text.endswith(".") else short_text + "."
    except requests.RequestException:
        pass

    try:
        html_url = f"https://en.wikipedia.org/wiki/{word}"
        r = requests.get(html_url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            paragraphs = [p.get_text(" ", strip=True) for p in soup.select("p") if p.get_text(strip=True)]
            for para in paragraphs:
                if "may refer to" in para.lower():
                    continue
                sentences = re.split(r"(?<=[.!?]) +", para)
                for s in sentences:
                    if re.search(r"\b(is|refers to|in)\b", s, re.IGNORECASE):
                        trimmed = ". ".join(sentences[:3]).strip()
                        return trimmed if trimmed.endswith(".") else trimmed + "."
            if paragraphs:
                return " ".join(paragraphs[0].split()[:60]) + "..."
    except requests.RequestException:
        pass
    return None

# ------------------ DEFINITIONS ------------------
def get_definition(word):
    """DictionaryAPI → Wiktionary → Wikipedia → WordNet chain (always returns some example/context)."""
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        r = requests.get(url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            data = r.json()
            meaning = data[0]['meanings'][0]
            d = meaning['definitions'][0]
            definition = d.get('definition')
            example = d.get('example')
            if definition:
                # If dictionary gives no example, we’ll fetch a wiki snippet instead
                if not example:
                    wiki_text = get_wikipedia_context(word)
                    if wiki_text:
                        example = wiki_text.split(". ")[1].strip() + "." if ". " in wiki_text else wiki_text
                return definition, example
    except requests.RequestException:
        pass

    # Wiktionary
    wiktionary_def = get_wiktionary_context(word)
    if wiktionary_def:
        wiki_text = get_wikipedia_context(word)
        example = wiki_text.split(". ")[0] + "." if wiki_text else None
        return wiktionary_def, example

    # Wikipedia
    wiki_text = get_wikipedia_context(word)
    if wiki_text:
        sentences = wiki_text.split(". ")
        definition = sentences[0].strip() + "."
        example = ". ".join(sentences[1:3]).strip() + "." if len(sentences) > 1 else None
        return definition, example

    # WordNet
    synsets = wordnet.synsets(word)
    if synsets:
        definition = synsets[0].definition()
        example = synsets[0].examples()[0] if synsets[0].examples() else None
        return definition, example

    return "Definition not found.", None


# ------------------ WORD SELECTION ------------------
def get_new_online_word():
    """Pick a never-before-sent word; reset if exhausted. Returns (word, topic)."""
    sent = get_sent_words()
    all_words, topic = get_random_words_from_datamuse(limit=200)

    if not all_words:
        all_words = [
            "lucid", "tenacious", "tranquil", "eloquent", "vivid",
            "candid", "austere", "prudent", "gregarious", "succinct",
            "serene", "amicable", "astute", "arduous", "cogent"
        ]
        topic = "general vocabulary"

    available = [w for w in all_words if w not in sent and len(w) > 4 and w.isalpha() and w.islower()]

    if not available:
        print("🎉 All fetched words used. Clearing log.")
        if os.path.exists("sent_words.json"):
            os.remove("sent_words.json")
        return get_new_online_word()

    word = random.choice(available)
    save_sent_word(word)
    return word, topic

# ------------------ EMAIL ------------------
def send_email(word, synonyms, definition, example=None, topic=None):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Word of the Day: {word}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENTS)

    if example and len(example) > 600:
        example = example[:600].rstrip() + "..."

    body = f"""Word of the Day: {word}
Topic: {topic if topic else 'general'}

Definition: {definition}

Synonyms: {', '.join(synonyms) if synonyms else '—'}"""

    if example:
        body += f"\n\nExample / Usage: {example}"

    body += "\n\nReply 'yes' if you would like to receive similar vocab or 'no' if not."

    msg.attach(MIMEText(body, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

    print(f"📧 Sent '{word}' (topic: {topic}) to: {', '.join(RECIPIENTS)}")

# ------------------ MAIN ------------------
if __name__ == "__main__":
    word, topic = get_new_online_word()
    synonyms = get_synonyms_from_datamuse(word)
    definition, example = get_definition(word)

    print(f"Selected word: {word}")
    print(f"Topic: {topic}")
    print(f"Definition: {definition}")
    if example:
        print(f"Example: {example[:160]}...")
    print(f"Synonyms: {synonyms}")

    send_email(word, synonyms, definition, example, topic)
