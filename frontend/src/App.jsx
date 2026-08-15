import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { BrowserRouter, Routes, Route, useLocation } from 'react-router-dom'
import { animate } from 'motion'
import Sidebar from './components/Sidebar'
import SceneCut from './components/SceneCut'
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
const ListeningHistory = lazy(() => import('./pages/ListeningHistory'))
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
  const mainRef = useRef(null)
  useEffect(() => { warmBackend() }, [])
  useEffect(() => {
    const el = routeRef.current
    if (!el) return
    el.scrollTo?.({ top: 0 })
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return

    const camera = {
      cartography: ['translate3d(-8px, 8px, 0) scale(1.008)', '50% 45%'],
      observatory: ['translate3d(8px, 5px, 0) scale(1.012)', '78% 35%'],
      song: ['translate3d(-5px, 9px, 0) scale(1.009)', '35% 40%'],
      lexicon: ['translate3d(0, 10px, 0) scale(1.006)', '30% 30%'],
      graph: ['translate3d(9px, 6px, 0) scale(1.012)', '65% 50%'],
      archive: ['translate3d(0, -6px, 0) scale(.995)', '50% 30%'],
      atlas: ['translate3d(0, 8px, 0) scale(1.009)', '50% 45%'],
      lost: ['translate3d(0, 6px, 0) scale(.995)', '50% 50%'],
    }[family]

    const contentMotion = animate(
      el,
      {
        opacity: [0, 1],
        transform: [camera[0], 'translate3d(0, 0, 0) scale(1)'],
        filter: ['blur(3px)', 'blur(0px)'],
      },
      { duration: 0.48, ease: [0.22, 1, 0.36, 1] },
    )
    const atmosphere = mainRef.current?.querySelector('.atlas-atmosphere')
    const atmosphereMotion = atmosphere
      ? animate(
          atmosphere,
          { opacity: [0.7, 1], transform: ['scale(1.012)', 'scale(1)'] },
          { duration: 0.65, ease: [0.22, 1, 0.36, 1] },
        )
      : null
    el.style.transformOrigin = camera[1]

    return () => {
      contentMotion?.stop?.()
      atmosphereMotion?.stop?.()
    }
  }, [pathname, family])
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
          ref={mainRef}
          // `overflow-x: hidden` forces overflow-y to `auto`, making this a
          // scroll container, which silently breaks every position: sticky
          // inside it. `clip` avoids that, so it is used from xl up where the
          // sticky asides live. Below xl we keep `hidden`: some routes
          // (/genre-weather) render elements a little wider than a 375px
          // viewport, and `hidden` absorbs that where `clip` would not.
          className="atlas-main flex-1 lg:ml-56 min-h-screen overflow-x-hidden xl:overflow-x-clip"
          data-atlas-scene={scene.key}
          data-atlas-family={family}
          style={{ '--route-accent': scene.accent }}
        >
          <RouteAtmosphere scene={scene} />
          <SceneCut scene={scene} />
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
            <Route path="/your-listening" element={<RoomPage roomId="your-listening" />} />
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
            <Route path="/listening" element={<ListeningHistory />} />
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
