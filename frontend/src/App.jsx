import { useState } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import Sidebar from './components/Sidebar'
import Home from './pages/Home'
import MoodMap from './pages/MoodMap'
import GenreWeather from './pages/GenreWeather'
import GroupBlend from './pages/GroupBlend'
import SoundtrackGift from './pages/SoundtrackGift'
import AncestryExplorer from './pages/AncestryExplorer'
import PlaylistForensics from './pages/PlaylistForensics'
import SixDegrees from './pages/SixDegrees'
import ArtistUbiquity from './pages/ArtistUbiquity'
import PlaylistLanguage from './pages/PlaylistLanguage'
import EditorialGraveyard from './pages/EditorialGraveyard'
import CooccurrenceCompass from './pages/CooccurrenceCompass'
import SongPassport from './pages/SongPassport'
import ArtistHabitat from './pages/ArtistHabitat'
import BasicnessIndex from './pages/BasicnessIndex'
import MoodContradiction from './pages/MoodContradiction'
import TransitionFinder from './pages/TransitionFinder'
import PlaylistDoppelganger from './pages/PlaylistDoppelganger'
import PlaylistRoast from './pages/PlaylistRoast'
import TimeCapsule from './pages/TimeCapsule'
import SongCollision from './pages/SongCollision'
import ForgottenHits from './pages/ForgottenHits'
import MainCharacter from './pages/MainCharacter'
import TrendExplorer from './pages/TrendExplorer'
import GuiltyPleasureMap from './pages/GuiltyPleasureMap'
import OverlapArena from './pages/OverlapArena'
import PlaylistNameGenerator from './pages/PlaylistNameGenerator'
import RoomPage from './pages/RoomPage'
import NotFound from './pages/NotFound'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)
  return (
    <BrowserRouter>
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
        <main className="flex-1 lg:ml-56 min-h-screen overflow-x-hidden">
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
        </main>
      </div>
    </BrowserRouter>
  )
}
