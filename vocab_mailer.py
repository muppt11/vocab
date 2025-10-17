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

# ------------------ ENV ------------------
load_dotenv()
SENDER_EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
RECIPIENTS = [email.strip() for email in os.getenv("RECIPIENTS", SENDER_EMAIL).split(",")]


# Common request settings
REQ_TIMEOUT = 5  # seconds

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

# ------------------ ONLINE FETCHERS ------------------
def get_random_words_from_datamuse(limit=200):
    """Fetch random-ish words. Filters to alphabetic only."""
    try:
        url = f"https://api.datamuse.com/words?sp=*&max={limit}"
        r = requests.get(url, timeout=REQ_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return [item["word"] for item in data if item.get("word", "").isalpha()]
    except requests.RequestException:
        pass
    return []

def get_synonyms_from_datamuse(word):
    try:
        url = f"https://api.datamuse.com/words?ml={word}"
        r = requests.get(url, timeout=REQ_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            return [item["word"] for item in data[:10]]
    except requests.RequestException:
        pass
    # Fallback to WordNet if API fails/empty
    syns = [lemma.name().replace('_', ' ')
            for syn in wordnet.synsets(word)
            for lemma in syn.lemmas()]
    return sorted(set(syns))[:10]

def get_definition(word):
    """Try DictionaryAPI first; fallback to WordNet; else stub."""
    # DictionaryAPI
    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        r = requests.get(url, timeout=REQ_TIMEOUT)
        if r.status_code == 200:
            data = r.json()
            try:
                d = data[0]['meanings'][0]['definitions'][0]['definition']
                if d:
                    return d
            except (KeyError, IndexError, TypeError):
                pass
    except requests.RequestException:
        pass
    # WordNet fallback
    synsets = wordnet.synsets(word)
    if synsets:
        return synsets[0].definition()
    return "Definition not found."

def get_new_online_word():
    """Pick a never-before-sent word from online list; reset if exhausted."""
    sent = get_sent_words()
    all_words = get_random_words_from_datamuse(limit=200)

    # fallback if the API is down
    if not all_words:
        all_words = [
            "lucid", "tenacious", "tranquil", "eloquent", "vivid",
            "candid", "austere", "prudent", "gregarious", "succinct",
            "serene", "amicable", "astute", "arduous", "cogent"
        ]

    available = [
        w for w in all_words
        if w not in sent and len(w) > 4 and w.isalpha() and w.islower()
    ]

    if not available:
        print("🎉 All fetched words have been used. Clearing log and starting fresh.")
        if os.path.exists("sent_words.json"):
            os.remove("sent_words.json")
        return get_new_online_word()

    word = random.choice(available)
    save_sent_word(word)
    return word

# ------------------ EMAIL ------------------
def send_email(word, synonyms, definition):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Word of the Day: {word}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = ", ".join(RECIPIENTS)

    text = f"""Word of the Day: {word}

Definition: {definition}

Synonyms: {', '.join(synonyms) if synonyms else '—'}

Reply 'yes' if you would like to receive similar vocab or 'no' if not.
"""
    msg.attach(MIMEText(text, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, RECIPIENTS, msg.as_string())

    print(f"Sent '{word}' to: {', '.join(RECIPIENTS)}")


# ------------------ MAIN ------------------
if __name__ == "__main__":
    word = get_new_online_word()
    synonyms = get_synonyms_from_datamuse(word)
    definition = get_definition(word)
    print(f"Selected word: {word}")
    print(f"Definition: {definition}")
    print(f"Synonyms: {synonyms}")
    send_email(word, synonyms, definition)
