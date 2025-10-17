from dotenv import load_dotenv
import os

load_dotenv()
SENDER_EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")
from dotenv import load_dotenv
import os

load_dotenv()
SENDER_EMAIL = os.getenv("EMAIL")
APP_PASSWORD = os.getenv("APP_PASSWORD")

import random
from nltk.corpus import wordnet

def get_word_and_synonyms():
    common_words = ["happy", "fast", "strong", "kind", "smart", "clear", "bright"]
    word = random.choice(common_words)
    synonyms = [lemma.name().replace('_', ' ')
                for syn in wordnet.synsets(word)
                for lemma in syn.lemmas()]
    synonyms = sorted(set(synonyms))[:5]
    return word, synonyms


import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

def send_email(word, synonyms):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Word of the Day: {word}"
    msg["From"] = SENDER_EMAIL
    msg["To"] = SENDER_EMAIL

    text = f"""Word of the Day: {word}
Synonyms: {', '.join(synonyms)}

Reply 'Y' if you like it or 'N' if not.
"""
    msg.attach(MIMEText(text, "plain"))

    context = ssl.create_default_context()
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=context) as server:
        server.login(SENDER_EMAIL, APP_PASSWORD)
        server.sendmail(SENDER_EMAIL, SENDER_EMAIL, msg.as_string())
    print(f"📧 Sent '{word}' to {SENDER_EMAIL}")



