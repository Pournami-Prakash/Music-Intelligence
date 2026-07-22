import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import { getScene } from './data/pageScenes'
import { warmBackend } from './lib/api'

const Home = lazy(() => import('./pages/Home'))
const MoodMap = lazy(() => import('./pages/MoodMap'))
const GenreWeather = lazy(() => import('./pages/GenreWeather'))
const GroupBlend = lazy(() => import('./pages/GroupBlend'))
const SoundtrackGift = lazy(() => import('./pages/SoundtrackGift'))
const AncestryExplorer = lazy(() => import('./pages/AncestryExplorer'))
const PlaylistForensics = lazy(() => import('./pages/PlaylistForensics'))
const SixDegrees = lazy(() => import('./pages/SixDegrees'))
const ArtistUbiquity = lazy(() => import('./pages/ArtistUbiquity'))
const PlaylistLanguage = lazy(() => import('./pages/PlaylistLanguage'))
const EditorialGraveyard = lazy(() => import('./pages/EditorialGraveyard'))
const CooccurrenceCompass = lazy(() => import('./pages/CooccurrenceCompass'))
const SongPassport = lazy(() => import('./pages/SongPassport'))
const ArtistHabitat = lazy(() => import('./pages/ArtistHabitat'))
const BasicnessIndex = lazy(() => import('./pages/BasicnessIndex'))
const MoodContradiction = lazy(() => import('./pages/MoodContradiction'))
const TransitionFinder = lazy(() => import('./pages/TransitionFinder'))
const PlaylistDoppelganger = lazy(() => import('./pages/PlaylistDoppelganger'))
const PlaylistRoast = lazy(() => import('./pages/PlaylistRoast'))
const TimeCapsule = lazy(() => import('./pages/TimeCapsule'))
const SongCollision = lazy(() => import('./pages/SongCollision'))
const ForgottenHits = lazy(() => import('./pages/ForgottenHits'))
const MainCharacter = lazy(() => import('./pages/MainCharacter'))
const TrendExplorer = lazy(() => import('./pages/TrendExplorer'))
const GuiltyPleasureMap = lazy(() => import('./pages/GuiltyPleasureMap'))
const OverlapArena = lazy(() => import('./pages/OverlapArena'))
const PlaylistNameGenerator = lazy(() => import('./pages/PlaylistNameGenerator'))
const RoomPage = lazy(() => import('./pages/RoomPage'))
const NotFound = lazy(() => import('./pages/NotFound'))

const SCENE_FAMILIES = {
  MAP: 'cartography',
  OBS: 'observatory',
  SPT: 'song',
  LEX: 'lexicon',
  TNL: 'graph',
  DRP: 'archive',
  ATLAS: 'atlas',
  ERR: 'lost',
}

function RouteAtmosphere({ scene }) {
  return (
    <div className="atlas-atmosphere" data-motif={scene.key} aria-hidden="true">
      <div className="atlas-route-stamp">
        <span>{scene.code}</span>
        <small>{scene.label}</small>
      </div>
      <div className="atlas-motif">
        <i className="atlas-shape atlas-shape-a" />
        <i className="atlas-shape atlas-shape-b" />
        <i className="atlas-shape atlas-shape-c" />
        <i className="atlas-shape atlas-shape-d" />
      </div>
      <div className="atlas-coordinate-rail">
        <span>playlist corpus</span>
        <span>66.3m relations</span>
        <span>live instrument</span>
      </div>
    </div>
  )
}

function AtlasShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const { pathname } = useLocation()
  const scene = getScene(pathname)
  const family = SCENE_FAMILIES[scene.code.split(' /')[0]] || 'lost'
  const routeRef = useRef(null)
  useEffect(() => { warmBackend() }, [])
  // Replay the route-enter animation on navigation without remounting the
  // subtree (remounting would re-trigger the lazy Suspense fallback flash).
  useEffect(() => {
    const el = routeRef.current
    if (!el) return
    el.classList.remove('atlas-route-enter')
    void el.offsetWidth        // force reflow so the animation restarts
    el.classList.add('atlas-route-enter')
    el.scrollTo?.({ top: 0 })
  }, [pathname])
  return (
      <div className="flex w-full min-h-screen bg-atlas-bg">
        <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
        {/* Mobile hamburger — hidden on lg+ where sidebar is always visible */}
        <button
          onClick={() => setSidebarOpen(true)}
          className="lg:hidden fixed top-3 left-3 z-50 w-9 h-9 flex items-center justify-center bg-black/80 border border-white/10 backdrop-blur"
          aria-label="Open navigation"
        >
          <span className="flex flex-col gap-[5px]">
            <span className="w-4 h-px bg-atlas-heading block" />
            <span className="w-4 h-px bg-atlas-heading block" />
            <span className="w-4 h-px bg-atlas-heading block" />
          </span>
        </button>
        <main
          className="atlas-main flex-1 lg:ml-56 min-h-screen overflow-x-hidden"
          data-atlas-scene={scene.key}
          data-atlas-family={family}
          style={{ '--route-accent': scene.accent }}
        >
          <RouteAtmosphere scene={scene} />
          <div className="atlas-route-content" ref={routeRef}>
            <Suspense fallback={<div className="min-h-screen grid place-items-center text-atlas-muted" role="status">Opening atlas room…</div>}>
            <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/artist-observatory" element={<RoomPage roomId="artist-observatory" />} />
            <Route path="/song-world" element={<RoomPage roomId="song-world" />} />
            <Route path="/vibe-dictionary" element={<RoomPage roomId="vibe-dictionary" />} />
            <Route path="/taste-tunnel" element={<RoomPage roomId="taste-tunnel" />} />
            <Route path="/drop-archive" element={<RoomPage roomId="drop-archive" />} />
            <Route path="/deep-map" element={<RoomPage roomId="deep-map" />} />
            <Route path="/mood-map" element={<MoodMap />} />
            <Route path="/genre-weather" element={<GenreWeather />} />
            <Route path="/group-blend" element={<GroupBlend />} />
            <Route path="/soundtrack-gift" element={<SoundtrackGift />} />
            <Route path="/ancestry" element={<AncestryExplorer />} />
            <Route path="/forensics" element={<PlaylistForensics />} />
            <Route path="/six-degrees" element={<SixDegrees />} />
            <Route path="/artist-ubiquity" element={<ArtistUbiquity />} />
            <Route path="/playlist-language" element={<PlaylistLanguage />} />
            <Route path="/editorial-graveyard" element={<EditorialGraveyard />} />
            <Route path="/compass" element={<CooccurrenceCompass />} />
            <Route path="/song-passport" element={<SongPassport />} />
            <Route path="/artist-habitat" element={<ArtistHabitat />} />
            <Route path="/basicness" element={<BasicnessIndex />} />
            <Route path="/mood-contradiction" element={<MoodContradiction />} />
            <Route path="/transition" element={<TransitionFinder />} />
            <Route path="/doppelganger" element={<PlaylistDoppelganger />} />
            <Route path="/roast" element={<PlaylistRoast />} />
            <Route path="/time-capsule" element={<TimeCapsule />} />
            <Route path="/collision" element={<SongCollision />} />
            <Route path="/forgotten-hits" element={<ForgottenHits />} />
            <Route path="/main-character" element={<MainCharacter />} />
            <Route path="/trend-explorer" element={<TrendExplorer />} />
            <Route path="/guilty-pleasure" element={<GuiltyPleasureMap />} />
            <Route path="/overlap-arena" element={<OverlapArena />} />
            <Route path="/name-generator" element={<PlaylistNameGenerator />} />
            <Route path="*" element={<NotFound />} />
            </Routes>
            </Suspense>
          </div>
        </main>
      </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AtlasShell />
    </BrowserRouter>
  )
}
