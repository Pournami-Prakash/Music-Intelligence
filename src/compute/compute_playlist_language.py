"""
Compute playlist title term frequencies from 1M playlist names.

Output: R2:computed/playlist_title_terms.parquet
Schema:
    term          str   — word or 2-gram
    count         int   — how many playlist names contain it
    pct           float — count / total_playlists * 100
    theme         str   — mood | activity | time | identity | genre | other
    example_titles list  — up to 5 example playlist names containing this term

Usage:
    python src/compute/compute_playlist_language.py
"""

import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent.parent / ".env")
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.storage.duckdb_r2 import get_con, R2_PATH
from src.storage.r2 import R2Client

R2_KEY = "computed/playlist_title_terms.parquet"

THEME_MAP = {
    'mood':     {'sad', 'happy', 'chill', 'vibe', 'vibes', 'love', 'angry', 'mood', 'feel',
                 'feelings', 'cry', 'crying', 'hype', 'energy', 'bop', 'bops', 'soft', 'dark',
                 'cozy', 'calm', 'emotional', 'deep', 'melancholy', 'heartbreak', 'healing'},
    'activity': {'workout', 'gym', 'study', 'studying', 'work', 'drive', 'driving', 'run',
                 'running', 'sleep', 'sleeping', 'party', 'dance', 'cooking', 'cleaning',
                 'focus', 'relax', 'relaxing', 'morning', 'roadtrip', 'road', 'trip'},
    'time':     {'3am', 'night', 'midnight', 'summer', 'winter', 'spring', 'fall', 'autumn',
                 'sunday', 'friday', 'monday', 'late', 'evening', 'afternoon', 'day', 'season'},
    'identity': {'girl', 'woman', 'boy', 'man', 'aesthetic', 'era', 'main', 'character',
                 'healing', 'diaspora', 'brown', 'black', 'queer', 'gay', 'indie', 'basic',
                 'baddie', 'soft', 'cottagecore', 'dark', 'academia'},
    'genre':    {'rap', 'hiphop', 'hip', 'hop', 'pop', 'rnb', 'rock', 'indie', 'country',
                 'jazz', 'classical', 'electronic', 'edm', 'metal', 'punk', 'soul', 'blues',
                 'reggae', 'latin', 'kpop', 'afrobeats', 'trap', 'lofi'},
}

STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'for', 'to', 'of', 'in', 'on', 'at', 'by',
    'with', 'from', 'my', 'your', 'our', 'its', 'this', 'that', 'is', 'are', 'was',
    'be', 'have', 'has', 'do', 'not', 'no', 'it', 'i', 'we', 'you', 'me', 'so',
    'just', 'more', 'some', 'all', 'new', 'good', 'best', 'hot', 'top', 'mix', 'music',
    'playlist', 'songs', 'song', 'list', 'hits', 'tracks', 'track',
}

MIN_COUNT = 50
TOP_N_TERMS = 500


def assign_theme(term: str) -> str:
    words = set(term.lower().split())
    for theme, keywords in THEME_MAP.items():
        if words & keywords:
            return theme
    return 'other'


def tokenize(name: str) -> list[str]:
    name = name.lower()
    name = re.sub(r'[^\w\s]', ' ', name)
    tokens = [t for t in name.split() if t not in STOPWORDS and len(t) >= 2 and not t.isdigit()]
    return tokens


def main():
    print("Loading playlist names from R2 via DuckDB...")
    con = get_con()
    df = con.execute(f"""
        SELECT pid, name
        FROM read_parquet('{R2_PATH}/processed/playlists.parquet')
        WHERE name IS NOT NULL AND length(trim(name)) > 0
    """).df()
    print(f"  {len(df):,} playlists loaded")

    total = len(df)
    names = df['name'].tolist()

    print("Tokenizing and counting terms...")
    term_counts: Counter = Counter()
    term_examples: dict[str, list[str]] = defaultdict(list)

    for name in names:
        tokens = tokenize(name)
        seen = set()
        for tok in tokens:
            if tok not in seen:
                term_counts[tok] += 1
                seen.add(tok)
        # 2-grams
        for i in range(len(tokens) - 1):
            bigram = f"{tokens[i]} {tokens[i+1]}"
            if bigram not in seen:
                term_counts[bigram] += 1
                seen.add(bigram)

    print(f"  {len(term_counts):,} unique terms found")

    # Collect examples (cap at 5 per term, for top terms only)
    top_terms = {t for t, c in term_counts.most_common(TOP_N_TERMS) if c >= MIN_COUNT}
    print(f"  Collecting examples for {len(top_terms):,} top terms...")
    for name in names:
        tokens_set = set(tokenize(name))
        for term in top_terms:
            words = set(term.split())
            if words <= tokens_set and len(term_examples[term]) < 5:
                term_examples[term].append(name)

    # Build output dataframe
    rows = []
    for term, count in term_counts.most_common(TOP_N_TERMS):
        if count < MIN_COUNT:
            continue
        rows.append({
            'term':           term,
            'count':          count,
            'pct':            round(count / total * 100, 3),
            'theme':          assign_theme(term),
            'example_titles': term_examples.get(term, []),
        })

    result = pd.DataFrame(rows)
    print(f"\n  Built {len(result):,} term rows")
    print(result.head(10).to_string(index=False))

    r2 = R2Client()
    tmp = Path(tempfile.gettempdir()) / 'playlist_title_terms.parquet'
    result.to_parquet(tmp, index=False, compression='zstd')
    r2.upload(tmp, R2_KEY, delete_after=True)
    r2.usage_summary()
    print(f"\n✓ Written to R2:{R2_KEY}")


if __name__ == '__main__':
    main()
