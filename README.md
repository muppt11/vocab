# vocab

A small Python script that emails a new vocabulary word every day, with a definition, an example, and synonyms. It never sends the same word twice.

## How it works

1. Picks a random topic (like science or philosophy) and a random starting letter, then asks the Datamuse API for matching words
2. Skips anything it has already sent, using `sent_words.json`
3. Gets a definition from Wikipedia, falling back to WordNet
4. Pulls synonyms from Datamuse, falling back to WordNet
5. Sends a formatted email through Gmail

## Run it

```bash
pip install -r requirements.txt
python -c "import nltk; nltk.download('wordnet')"
```

Create a `.env` file (it's gitignored, never commit it):

```
EMAIL=you@gmail.com
APP_PASSWORD=your-gmail-app-password
RECIPIENTS=friend1@example.com,friend2@example.com
```

Then run `python vocab_mailer.py`, or schedule it daily with cron.

## Challenges

**The APIs don't always cooperate.** Some topic and letter combos return almost nothing. I added three layers of fallbacks (topic plus letter, then topic only, then any word) so there's always something to send.

**Wikipedia isn't a dictionary.** Lots of words land on "may refer to" disambiguation pages. The script detects those and falls back to WordNet instead of sending a useless definition.

**Not repeating myself.** Random picks repeat surprisingly fast, so every sent word is logged and filtered out next time.
