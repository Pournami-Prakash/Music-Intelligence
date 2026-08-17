export const ROOMS = {
  'deep-map': {
    name: 'Deep Map',
    eyebrow: 'Atlas research',
    accent: '#7AB89A',
    code: 'MAP',
    icon: 'Home',
    description: 'The large-format research wing: mood regions, genre weather, ancestry, forensics, and group taste.',
    primary: ['Open Mood Map', '/mood-map', {}],
    stats: ['mood regions', 'genre drift', 'lineage'],
    features: [
      ['Mood Map', '/mood-map', 'How playlist language clustered into moods, 2010–2017.', {}, 'Globe'],
      ['Genre Neighborhoods', '/genre-weather', 'Compare genre regions by cluster proximity and evidence size.', {}, 'CloudRain'],
      ['Tag Lineage', '/ancestry', 'Compare tag-similar artists across playlist-reach tiers.', {}, 'GitBranch'],
      ['Editorial Overlap', '/forensics', 'Measure how much of a public playlist appears in the editorial reference set.', {}, 'Search'],
    ],
  },
  'artist-observatory': {
    name: 'Artist Observatory',
    eyebrow: 'Identity weather',
    accent: '#34D399',
    code: 'OBS',
    description: 'A place to read artists as cultural signals: reach, habitats, mainstream gravity, and overlap.',
    primary: ['Start with Ubiquity', '/artist-ubiquity', { artist: 'Taylor Swift' }],
    stats: ['artist reach', 'playlist habitats', 'overlap field'],
    features: [
      ['Ubiquity', '/artist-ubiquity', 'How far does an artist travel across 1M playlists?', { artist: 'Taylor Swift' }, 'BarChart2'],
      ['Habitat', '/artist-habitat', 'Where does this artist actually live: gym, sad, party, study?', { artist: 'Drake' }, 'MapPin'],
      ['Basicness', '/basicness', 'How mainstream is the artist in playlist culture?', { query: 'Ed Sheeran' }, 'Gauge'],
      ['Reach Score', '/main-character', 'Place an artist in the archive’s playlist-reach percentile.', { query: 'Taylor Swift' }, 'TrendingUp'],
      ['Overlap', '/overlap-arena', 'Compare two artists head-to-head by playlist footprint.', { a: 'Drake', b: 'Taylor Swift' }, 'Trophy'],
    ],
  },
  'song-world': {
    name: 'Song World',
    eyebrow: 'Track customs',
    accent: '#62A8FF',
    code: 'SPT',
    description: 'Search a song and inspect its public life: where it travels, what moods misuse it, and how it behaves across contexts.',
    primary: ['Stamp a song', '/song-passport', { track: 'Mr. Brightside' }],
    stats: ['track habitats', 'contradictions', 'gift signals'],
    features: [
      ['Passport', '/song-passport', 'A track biography through playlist titles and companions.', { track: 'Mr. Brightside' }, 'BookOpen'],
      ['Cross-Context', '/mood-contradiction', 'Tracks shared by contrasting playlist-title contexts.', { mood: 'sad' }, 'Zap'],
      ['Context Switchers', '/guilty-pleasure', 'Compare where the same tracks cross between named contexts.', {}, 'Heart'],
      ['Gift', '/soundtrack-gift', 'Turn a feeling into a playlist to send someone.', {}, 'Gift'],
    ],
  },
  'vibe-dictionary': {
    name: 'Vibe Dictionary',
    eyebrow: 'Playlist language',
    accent: '#FB923C',
    code: 'LEX',
    // Title-derived, so permanently bounded by the corpus: a million
    // user-written playlist names from 2010-2017, which no current source
    // replaces. Dated rather than quietly presented as the present tense.
    description: 'How a million people named their playlists between 2010 and 2017: words, titles, eras, naming rituals, and cultural shorthand.',
    primary: ['Open the corpus', '/playlist-language', {}],
    stats: ['1M titles', 'word frequency', 'naming rituals'],
    features: [
      ['Language', '/playlist-language', 'The vocabulary of 1M playlist names, 2010–2017 — and how yours compares.', {}, 'Type'],
      ['Trend Words', '/trend-explorer', 'Search any word and read its variants and edges, 2010–2017.', { term: 'vibes' }, 'Search'],
      ['Name Gen', '/name-generator', 'Generate names from real 2010s playlist language.', {}, 'Wand2'],
      ['Roast', '/roast', 'See how generic a playlist title was in the 2010s.', { title: 'vibes' }, 'Flame'],
    ],
  },
  'taste-tunnel': {
    name: 'Taste Tunnel',
    eyebrow: 'Connection graph',
    accent: '#C084FC',
    code: 'TNL',
    description: 'The graph room: artist paths, co-occurrence orbits, collisions, transitions, and sonic twins.',
    primary: ['Find a route', '/six-degrees', { from: 'Drake', to: 'Radiohead' }],
    stats: ['66M co-occurrences', 'artist paths', 'taste bridges'],
    features: [
      ['Six Degrees', '/six-degrees', 'Find a bounded co-occurrence path between two artists.', { from: 'Drake', to: 'Radiohead' }, 'Network'],
      ['Compass', '/compass', 'Map the artists orbiting a central artist.', { artist: 'The Weeknd' }, 'Compass'],
      ['Collision', '/collision', 'How much two artists\' playlist footprints overlap.', { a: 'Taylor Swift', b: 'Kendrick Lamar' }, 'Swords'],
      ['Transition', '/transition', 'Bridge two songs in a few playlist-native steps.', { from: 'No Surprises', to: 'Mr. Brightside' }, 'ArrowLeftRight'],
      ['Doppelganger', '/doppelganger', 'Find an artist\'s closest sonic doppelgängers.', { artist: 'Drake' }, 'Copy'],
      ['Group Blend', '/group-blend', 'Find the artists in the intersection of several tastes.', {}, 'Shuffle'],
    ],
  },
  'drop-archive': {
    name: 'Drop Archive',
    eyebrow: 'Editorial afterlife',
    accent: '#94A3B8',
    code: 'DRP',
    description: 'A record of songs that rose, disappeared, got dropped, or became culturally stale.',
    primary: ['Open graveyard', '/editorial-graveyard', {}],
    stats: ['editorial removals', 'forgotten hits', 'era drift'],
    features: [
      ['Graveyard', '/editorial-graveyard', 'Tracks removed from Spotify editorial playlists.', {}, 'Archive'],
      ['Forgotten Hits', '/forgotten-hits', 'Songs that lost playlist gravity.', {}, 'Star'],
      ['Time Capsule', '/time-capsule', 'The songs, artists, and chart moments that defined each era.', {}, 'Clock'],
    ],
  },
  // The only room built from the visitor's own data rather than the corpus.
  // Everything in it is parsed in the browser and never uploaded.
  'your-listening': {
    name: 'Your Listening',
    eyebrow: 'Personal record',
    accent: '#3DDC97',
    code: 'YOU',
    icon: 'Clock',
    description: 'The one room made from your own data: drop in a Spotify export and read your listening against the corpus.',
    primary: ['Read your history', '/listening', {}],
    stats: ['your hours', 'taste drift', 'corpus placement'],
    features: [
      ['Listening History', '/listening', 'Your own export, read in the browser and never uploaded.', {}, 'Clock'],
    ],
  },
}

export const ROOM_ORDER = [
  'deep-map',
  'artist-observatory',
  'song-world',
  'vibe-dictionary',
  'taste-tunnel',
  'drop-archive',
  'your-listening',
]
