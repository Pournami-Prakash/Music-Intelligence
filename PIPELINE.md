# Pipeline Reference

Artifact dependency graph and run order for Music Intelligence Atlas.
All scripts are run from the repo root: `python src/compute/<script>.py`

## Artifact Map

```
MPD raw JSON
    └─► src/ingestion/ingest_mpd.py
            └─► processed/playlist_tracks.parquet
                    └─► src/ingestion/build_canonical_tracks.py
                                └─► processed/canonical_tracks.parquet   ← SPINE

                                            │
                                            ├─► compute_artist_edges.py
                                            │       └─► computed/artist_edges.parquet
                                            │               └─► compute_artist_stats.py
                                            │                       └─► computed/artist_stats.parquet
                                            │
                                            ├─► [ISRC enrichment]
                                            │       compute_mbdump_isrc.py
                                            │       compute_deezer_isrc.py --resume
                                            │       compute_mb_search_isrc.py
                                            │       └─► merge_isrc_enrichment.py
                                            │               └─► canonical_tracks.parquet (isrc filled)
                                            │
                                            └─► promote_mbid_canonical.py
                                                    ├─► canonical_tracks.parquet (mbid, listen_count, flags)
                                                    └─► computed/data_manifest.json

Mackorone editorial data
    └─► src/ingestion/ingest_mackorone.py
            └─► processed/editorial_playlists.parquet
                processed/editorial_playlist_tracks.parquet
                    └─► clean_editorial_tracks.py
                            └─► compute_editorial_summary.py
                                    └─► computed/editorial_removed.parquet

Last.fm enrichment
    └─► compute_lastfm_enrichment.py     (artist tags, listener counts → enrichment/artist_lastfm.parquet)
    └─► patch_artist_genres_lastfm.py    (fills empty rows in artist_genres.parquet)
    └─► compute_lastfm_habitat_signal.py (blends Last.fm tags into artist_habitat)

ListenBrainz
    └─► compute_listenbrainz_full.py
            └─► enrichment/listenbrainz_full.parquet

Deezer release dates
    └─► compute_release_dates.py
            └─► canonical_tracks.parquet (release_year column filled for ~124K tracks)
                    └─► compute_era_tracks.py
                                └─► computed/era_tracks.parquet

Track statistics
    └─► compute_track_stats.py
            └─► computed/track_stats.parquet  (2.26M tracks × playlist_count, top_playlist_names)

Artist habitat
    └─► compute_artist_habitat.py      (playlist-title keyword signal)
    └─► compute_lastfm_habitat_signal.py  (adds Last.fm tag signal → 21K artists total)

Track2Vec embeddings
    └─► src/embeddings/train_track2vec.py
            └─► embeddings/track2vec_vocab.parquet
                embeddings/track2vec_128.npy
                    └─► src/embeddings/project_umap.py
                                └─► embeddings/genre_umap.parquet
                                    embeddings/genre_umap_clusters.parquet

FAISS index
    └─► compute_faiss_index.py
            └─► embeddings/track2vec_hnsw.faiss
```

## Run Order (first-time setup)

```
Phase 0 — Ingest raw data
  python src/ingestion/ingest_mpd.py
  python src/ingestion/ingest_mackorone.py

Phase 1 — Build spine
  python src/ingestion/build_canonical_tracks.py
  python src/compute/compute_artist_edges.py      # must run before artist_stats
  python src/compute/compute_artist_stats.py

Phase 2 — ISRC enrichment (can run in parallel)
  python src/compute/compute_mbdump_isrc.py
  python src/compute/compute_deezer_isrc.py --resume
  python src/compute/compute_mb_search_isrc.py

Phase 3 — Merge enrichment into spine
  python src/compute/merge_isrc_enrichment.py
  python src/compute/compute_release_dates.py
  python src/compute/promote_mbid_canonical.py    # writes data_manifest.json

Phase 4 — Computed artifacts
  python src/compute/clean_editorial_tracks.py
  python src/compute/dedup_deezer_tracks.py
  python src/compute/compute_listenbrainz_full.py
  python src/compute/compute_lastfm_enrichment.py
  python src/compute/patch_artist_genres_lastfm.py

Phase 5 — Pre-compute tables for fast API responses
  python src/compute/compute_editorial_summary.py
  python src/compute/compute_track_stats.py
  python src/compute/compute_era_tracks.py
  python src/compute/compute_mood_map.py
  python src/compute/compute_artist_habitat.py
  python src/compute/compute_lastfm_habitat_signal.py

Phase 6 — Embeddings (slow, run overnight)
  python src/embeddings/train_track2vec.py
  python src/embeddings/project_umap.py
  python src/compute/compute_faiss_index.py
```

## R2 Key Layout

```
processed/
  canonical_tracks.parquet           # identity spine — primary artifact
  playlist_tracks.parquet            # raw MPD track-to-playlist rows (806 MB)
  editorial_playlists.parquet
  editorial_playlist_tracks.parquet

computed/
  artist_stats.parquet               # top 10K artists — popularity + co-artist graph
  artist_edges.parquet               # co-occurrence adjacency (a_name, b_name, shared_playlists)
  artist_habitat.parquet             # 21K artists × 8 habitat scores
  artist_images.parquet              # Spotify artist image URLs (cached)
  editorial_removed.parquet          # 2.5M removed tracks, pre-joined with playlist names
  track_stats.parquet                # 2.26M tracks × playlist_count + top_playlist_names
  era_tracks.parquet                 # 77K tracks with release_year + playlist_count
  mood_map_clusters.parquet
  playlist_title_terms.parquet
  data_manifest.json                 # coverage stats; read by /api/stats

enrichment/
  artist_genres.parquet              # MusicBrainz genre tags (10K artists)
  artist_lastfm.parquet              # Last.fm listener counts + tags (32K artists)
  chart_history.parquet              # Spotify chart history 2017–2026
  deezer_tracks.parquet              # Deezer metadata including release_date
  fma_enrichment.parquet
  listenbrainz_full.parquet          # 755K tracks with listen_count + recording_mbid
  listenbrainz_top_artists.parquet

embeddings/
  track2vec_128.npy                  # 599K tracks × 128 dims
  track2vec_hnsw.faiss               # HNSW index for <5ms similarity queries
  track2vec_vocab.parquet            # idx ↔ track_uri/name/artist mapping
  genre_umap.parquet                 # 2D UMAP projection of all 599K tracks
  genre_umap_clusters.parquet        # 308 genre clusters → 30 genre groups
```

## Key Constraints

- **R2 free tier: 10 GB hard limit** — never store raw dumps or intermediates in R2.
- All parquets use `compression="zstd"` to match existing artifacts.
- Long-running scripts checkpoint and support `--resume`.
- The API (main.py) reads exclusively from R2 via `_load_computed()` — never local disk directly.
- `.env` is never committed. Use `.env.example` as the template.

## Quality Checks

```bash
# Smoke-test all API endpoints (requires a running server)
BASE_URL=http://localhost:8000 pytest src/tests/test_smoke.py -v -m "not slow"

# Full data quality audit across R2 artifacts
python src/compute/check_data_quality.py --verbose
```
