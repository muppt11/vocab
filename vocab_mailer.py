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
    Fetch random words filtered by both topic and random starting letter.
    Keeps topic label but ensures varied results.
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

    # final fallback
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

# ------------------ DEFINITIONS ------------------
def get_definition(word):
    """Wikipedia first → WordNet fallback. Clean and modern output."""
    definition, example = None, None

    # --- Wikipedia summary ---
    try:
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{word}"
        r = requests.get(api_url, timeout=REQ_TIMEOUT, headers=REQ_HEADERS)
        if r.status_code == 200:
            data = r.json()
            extract = data.get("extract")
            if extract and "may refer to" not in extract.lower():
                sentences = extract.split(". ")
                definition = sentences[0].strip() + "."
                if len(sentences) > 1:
                    example = ". ".join(sentences[1:3]).strip() + "."
    except requests.RequestException:
        pass

    # --- WordNet fallback ---
    if not definition:
        synsets = wordnet.synsets(word)
        if synsets:
            definition = synsets[0].definition().capitalize() + "."
            if synsets[0].examples():
                example = synsets[0].examples()[0]

    # --- synthetic example ---
    if not example and definition:
        example = f"He used the word '{word}' to illustrate its meaning in context."

    # --- final fallback ---
    if not definition:
        definition = "Definition not found."

    return definition, example

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
    msg["Subject"] = f"Tanvi's Word of the Day [{topic.title() if topic else 'General'}]: {word.capitalize()}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENTS)

    if example and len(example) > 600:
        example = example[:600].rstrip() + "..."

    # HTML email template
    html = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.5; color: #333;">
        <h2 style="color:#fc8f00;">Word of the Day: <em>{word.capitalize()}</em></h2>
        <p><strong>Topic:</strong> {topic.title() if topic else 'General'}</p>
        <p><strong>Definition:</strong> {definition}</p>
        <p><strong>Synonyms:</strong> {', '.join(synonyms) if synonyms else '—'}</p>
        <p><strong>Example / Usage:</strong> {example}</p>
        <hr>
        <p style="font-size: 0.9em; color: #777;">
          Reply 'yes' if you would like to receive similar vocab, or 'no' if not.
        </p>
      </body>
    </html>
    """

    msg.attach(MIMEText(html, "html"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

    print(f"Sent '{word}' (topic: {topic}) to: {', '.join(RECIPIENTS)}")

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
