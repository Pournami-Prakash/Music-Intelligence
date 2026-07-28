export const FEATURE_PROFILES = {
  mood: {
    kind: 'territory',
    instrument: 'Territory sampler',
    readout: '8 mood regions',
    note: 'language clustered by emotional proximity',
  },
  weather: {
    kind: 'pressure',
    instrument: 'Pressure chamber',
    readout: 'genre drift',
    note: 'cultural fronts moving through playlist space',
  },
  ancestry: {
    kind: 'lineage',
    instrument: 'Lineage projector',
    readout: 'past ↔ future',
    note: 'influence branches across neighboring artists',
  },
  forensics: {
    kind: 'scanner',
    instrument: 'Curation scanner',
    readout: 'signal integrity',
    note: 'sequence, repetition, and authorship under review',
  },
  ubiquity: {
    kind: 'radar',
    instrument: 'Reach radar',
    readout: '1M playlists',
    note: 'measuring how far an artist travels',
  },
  habitat: {
    kind: 'bubbles',
    instrument: 'Habitat sampler',
    readout: 'context share',
    note: 'where an artist actually lives',
  },
  gauge: {
    kind: 'gauge',
    instrument: 'Gravity meter',
    readout: '0—100',
    note: 'mainstream pull calibrated to the archive',
  },
  spotlight: {
    kind: 'spotlight',
    instrument: 'Centrality lens',
    readout: 'persona rank',
    note: 'measuring cultural main-character energy',
  },
  overlap: {
    kind: 'overlap',
    instrument: 'Territory arena',
    readout: 'A ∩ B',
    note: 'two audiences entering the same field',
  },
  passport: {
    kind: 'passport',
    instrument: 'Context customs',
    readout: 'track visa',
    note: 'documenting where a song travels',
  },
  contradiction: {
    kind: 'fault',
    instrument: 'Intent comparator',
    readout: 'mood / reality',
    note: 'finding emotional placement failures',
  },
  guilty: {
    kind: 'heat',
    instrument: 'Survival grid',
    readout: 'context-proof',
    note: 'songs that survive every taste identity',
  },
  gift: {
    kind: 'arc',
    instrument: 'Emotion sequencer',
    readout: 'brief → arc',
    note: 'turning a relationship into a soundtrack',
  },
  language: {
    kind: 'matrix',
    instrument: 'Phrase corpus',
    readout: '1M titles',
    note: 'playlist culture speaking in aggregate',
  },
  trend: {
    kind: 'trend',
    instrument: 'Word gravity',
    readout: 'phrase velocity',
    note: 'tracking language as it gathers mass',
  },
  generator: {
    kind: 'slots',
    instrument: 'Naming machine',
    readout: 'corpus remix',
    note: 'real playlist language recombined',
  },
  roast: {
    kind: 'score',
    instrument: 'Originality audit',
    readout: 'genericity',
    note: 'measuring a title against the crowd',
  },
  degrees: {
    kind: 'path',
    instrument: 'Shortest-path finder',
    readout: 'artist route',
    note: 'playlist bridges between distant worlds',
  },
  compass: {
    kind: 'compass',
    instrument: 'Orbit compass',
    readout: 'co-occurrence',
    note: 'the artists surrounding a central signal',
  },
  collision: {
    kind: 'impact',
    instrument: 'Audience collider',
    readout: 'shared field',
    note: 'two footprints meeting at speed',
  },
  transition: {
    kind: 'bridge',
    instrument: 'Mix bridge',
    readout: 'track → track',
    note: 'finding a playlist-native route',
  },
  mirror: {
    kind: 'mirror',
    instrument: 'Twin scanner',
    readout: 'nearest signal',
    note: 'searching for an artist’s reflected self',
  },
  blend: {
    kind: 'blend',
    instrument: 'Consensus mixer',
    readout: 'shared lane',
    note: 'several tastes resolving together',
  },
  graveyard: {
    kind: 'ledger',
    instrument: 'Removal ledger',
    readout: 'editorial exit',
    note: 'songs after their programmed afterlife',
  },
  forgotten: {
    kind: 'decay',
    instrument: 'Gravity decay',
    readout: 'long-run loss',
    note: 'chart memory fading through time',
  },
  capsule: {
    kind: 'capsule',
    instrument: 'Era chamber',
    readout: '1960s—2020s',
    note: 'playlist history sealed by decade',
  },
}

export function getFeatureProfile(sceneKey) {
  return FEATURE_PROFILES[sceneKey] || null
}
