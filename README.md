# Music Intelligence Atlas

**A cultural map of how a million playlists actually use music.**

🔗 **[Explore the Atlas →](https://music-intelligence-blue.vercel.app)**

---

Streaming services describe songs by genre and audio features. That misses the
part that carries the meaning: *where people put a song.* A track filed under
"gym" and "heartbreak" by the same listeners is telling you something no BPM
value can.

The Atlas reads one million public playlists as cultural evidence. It maps where
artists travel, which contexts a song straddles, what vocabulary people reach
for when naming a mood, and which songs the editors quietly removed. Every
number traces back to playlist co-occurrence in a fixed corpus — not to
audio analysis, not to a recommender, and not to a model's opinion.

## The corpus

| | |
|---|---:|
| Playlists | 1,000,000 |
| Distinct tracks | 3,620,989 |
| Playlist–track rows | 66,346,428 |
| Editorial playlists archived | 9,053 |
| Artists with full profiles | 10,000 |
| Searchable track index | 2,262,292 |
| Track embeddings (128-dim) | 599,341 |
| ISRC coverage | 758,503 (20.9%) |
| MusicBrainz ID coverage | 693,171 (19.1%) |

Built on the Spotify Million Playlist Dataset as the spine, enriched with
MusicBrainz, ListenBrainz, Last.fm, and Deezer, plus an archive of editorial
playlist history. Corpus snapshot: **11 July 2026**.

## What you can do

Twenty-six views, grouped into six rooms.

**🗺️ Deep Map** — the research wing. Mood regions across the title corpus, genre
weather from an embedding projection, artist ancestry by shared-tag similarity,
playlist forensics against the editorial archive, and group blending.

**🔭 Artist Observatory** — read artists as cultural signals. Playlist reach and
rank, habitat (which contexts an artist lives in), a basicness percentile,
main-character scoring, and head-to-head overlap.

**🌍 Song World** — inspect one song's public life. Its passport of playlist
appearances, and the contexts it contradicts — tracks filed under both "happy"
and "heartbreak" by different people.

**📖 Vibe Dictionary** — the language layer. The vocabulary of a million playlist
titles, word trend exploration, a name generator trained on real naming habits,
and a title-genericness roast.

**🔗 Taste Tunnel** — the graph. Bounded co-occurrence paths between any two
artists, orbital compasses, collision analysis, transition routing between two
tracks, and embedding-based doppelgängers.

**🗄️ Drop Archive** — songs that rose, vanished, or got cut. Forgotten hits,
era time capsules, and the editorial graveyard of removed tracks.

## Every claim shows its work

Each view ships an **evidence contract** stating four things in plain language:
the exact metric, its source, what it covers, and — critically — what it does
*not* mean. Ancestry says outright that it does not infer influence or artistic
descent. Ubiquity says playlist reach is not listener count. Basicness says it's
a reach index, not a taste judgment.

Coverage limits are disclosed rather than hidden. Similarity search runs over the
most-playlisted tracks, so the long tail returns honest empties instead of
plausible fabrications. Views served from precomputed snapshots say so.

This is the part of the project I'd point at first. Anything can render a chart;
the harder discipline is refusing to overclaim what a chart means.

## How it's built

A **React + Vite** frontend with `motion` and `d3`, deployed on Vercel.

A **FastAPI** backend that queries **DuckDB** directly over Parquet artifacts in
**Cloudflare R2**, streaming rather than loading them — the serving layer holds
no dataset in memory. Vector similarity runs on **Upstash Vector**; a single
LLM-assisted feature uses **Groq**, with a deterministic keyword fallback when
the model is unavailable.

Everything expensive is precomputed offline: a track2vec embedding space, a UMAP
projection clustered into genre regions, artist co-occurrence graphs, habitat
scores, and per-era snapshots. The API only ever reads.

The serving layer was tuned hard for small hosts — serialized query execution,
bounded in-flight requests, an LRU result cache, jemalloc to stop heap
fragmentation, and graceful `503 + Retry-After` load-shedding instead of an
unbounded queue.

## Known limits

- Playlist co-occurrence measures **placement, not listening**. Reach is not popularity.
- Mood and context categories are **keyword-defined** from playlist titles. No audio, lyrics, or sentiment analysis is involved.
- Rich artist detail covers the top 10,000 artists; exact rank and reach cover the full table.
- Similarity features index the most-playlisted tracks, so obscure queries return empty rather than guessing.
- The corpus is a **fixed snapshot**, not a live feed. It does not track current charts.

---

*Data-pipeline reference lives in `PIPELINE.md`; operational notes are under `docs/` and `deploy/`.*
