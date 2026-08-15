# Music Intelligence Atlas

**[music-intelligence-blue.vercel.app →](https://music-intelligence-blue.vercel.app)**

Spotify will tell you a song is 122 BPM, in A minor, with high danceability. It
won't tell you that people put it on gym playlists *and* heartbreak playlists,
which is the more interesting fact about it.

That gap is what this project is about. A playlist is someone deciding a song
belongs somewhere: next to these other songs, under this name, for this
occasion. Do that a million times and you get a map of how music is actually
used, rather than how it's catalogued.

So I took a million public playlists and read them as cultural evidence.

## What falls out of it

Some of it confirms what you'd guess. Drake sits at rank one, appearing in
203,345 playlists, one in every five. The most common word in a playlist title
isn't a mood or a genre you'd expect; it's *country*, at 2.3% of all titles,
just ahead of *summer* and *chill*.

Some of it is stranger. Drake and Radiohead, two artists with roughly nothing
in common, are a single hop apart, sharing 2,167 playlists between them.
Olivia Rodrigo's "drivers license" turns up in eight times as many contrary-mood
playlists as the mood it supposedly belongs to. Songs refuse to stay in their
lane, and the playlist record is where you can see it happening.

The Atlas has twenty-six ways to poke at this, grouped into six rooms. The
**Deep Map** handles the big-picture work: mood regions, genre weather, artist
ancestry, forensics against the editorial archive. The **Artist Observatory**
reads artists as signals: reach, habitat, mainstream gravity, head-to-head
overlap. **Song World** takes a single track and shows you its public life.
The **Vibe Dictionary** is the language layer, where playlist titles become a
vocabulary you can search. **Taste Tunnel** is the graph: paths, orbits,
collisions, transitions, sonic twins. And the **Drop Archive** keeps the
receipts on songs that rose, vanished, or got quietly cut by an editor.

## The part I'd want you to look at

It's easy to render a chart. It's harder to be honest about what the chart means,
and that's where most data projects quietly cheat.

Every view here ships an *evidence contract*: the exact metric, its source, its
coverage, and what it does **not** mean. That last one is the part that usually
goes missing. Artist ancestry says outright that it infers nothing about influence or artistic
descent. Ubiquity says playlist reach is not listener count. The basicness index
says it's a measure of reach, not a judgment of taste.

Coverage limits get disclosed instead of papered over. Similarity search runs
over the most-playlisted tracks, so an obscure query returns an honest empty
rather than a confident fabrication. Views served from precomputed snapshots
say so. Nothing here measures listening, only placement, and every page
that could be misread as popularity says as much on its face.

I care more about that discipline than about any individual feature.

## Under it

A million playlists, 3.6 million distinct tracks, and 66.3 million
playlist-track rows, with the Spotify Million Playlist Dataset as the spine and
MusicBrainz, ListenBrainz, Last.fm, and Deezer filling in identity and
enrichment. Roughly a fifth of tracks carry a resolved ISRC or MusicBrainz ID.
The corpus is a fixed snapshot, frozen 11 July 2026. It's a map, not a ticker.

The frontend is React and Vite, with `motion` and `d3` doing the moving parts.
The backend is FastAPI, but the interesting choice is that it holds no dataset
in memory at all: DuckDB queries Parquet artifacts directly out of Cloudflare R2
and streams the results. Vector similarity lives in Upstash. One feature is
LLM-assisted through Groq, and it falls back to deterministic keyword logic the
moment the model is unavailable.

That architecture wasn't an aesthetic preference. The whole thing was built to
run on hosts with 512 MB of RAM, which meant serialized queries, bounded
in-flight requests, an LRU result cache, jemalloc to stop the heap fragmenting,
and shedding load with a `503` rather than growing a queue nobody's going to
wait on. Most of the engineering in this repo is that fight, and the load-test
notes recording where it was won and lost are still in `deploy/`.
