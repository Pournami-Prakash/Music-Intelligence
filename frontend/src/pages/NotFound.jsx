import { Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import LottiePlayer from '../components/LottiePlayer'
import { PvPage, PvTop } from '../components/Premium'

export default function NotFound() {
  return (
    <PvPage>
      <PvTop sub="Unmapped room" pill="404" />
      <div className="max-w-2xl mx-auto text-center" style={{ paddingTop: '6vh' }}>
        <LottiePlayer src="/assets/not-found-cat.json" className="w-64 h-64 mx-auto" />
        <h1 className="text-4xl sm:text-5xl font-extrabold tracking-[-0.03em] text-[var(--text-hi)] mt-2">This room isn't on the atlas.</h1>
        <p className="text-[var(--text-mid)] mt-4 leading-relaxed">
          Nothing broke — this address just doesn't point to a built feature yet. Head back to the main atlas or pick a mapped room from the sidebar.
        </p>
        <Link
          to="/"
          className="mt-8 inline-flex items-center gap-2 rounded-full px-5 py-2.5 text-sm font-semibold"
          style={{ background: 'var(--accent)', color: '#04140D' }}
        >
          <ArrowLeft size={15} /> Back to Atlas
        </Link>
      </div>
    </PvPage>
  )
}
