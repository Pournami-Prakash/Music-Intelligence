import { NavLink, useLocation } from 'react-router-dom'
import { ROOM_ORDER, ROOMS } from '../data/rooms'
import { ICONS } from '../lib/icons'

function NavItem({ to, icon, label, onClose }) {
  const Icon = ICONS[icon] || Compass
  return (
    <NavLink
      to={to}
      end={to === '/'}
      title={label}
      onClick={onClose}
      className={({ isActive }) =>
        `flex flex-row items-center justify-start gap-3 px-4 py-2.5 mb-0.5 transition-all border-l-2 ${
          isActive
            ? 'bg-atlas-lime/12 text-atlas-lime border-atlas-lime'
            : 'text-atlas-muted border-transparent hover:text-atlas-heading hover:bg-white/[0.045]'
        }`
      }
    >
      <Icon size={15} className="flex-shrink-0" />
      <span className="text-xs font-display font-bold tracking-tight leading-none truncate">
        {label}
      </span>
    </NavLink>
  )
}

function SectionLabel({ to, room, expanded, onClose }) {
  return (
    <NavLink
      to={to}
      title={room.name}
      onClick={onClose}
      aria-expanded={expanded}
      className={({ isActive }) =>
        `flex items-center justify-between text-[9px] font-display font-bold uppercase tracking-[0.2em] px-4 pt-3 pb-2 transition-colors ${
          isActive || expanded ? 'text-atlas-lime' : 'text-atlas-muted/50 hover:text-atlas-muted'
        }`
      }
    >
      <span>{room.name}</span>
      <span className="text-[7px] opacity-40">{expanded ? '−' : '+'}</span>
    </NavLink>
  )
}

export default function Sidebar({ isOpen, onClose }) {
  const { pathname } = useLocation()
  const activeRoomId = ROOM_ORDER.find(id =>
    pathname === `/${id}` || ROOMS[id].features.some(([, to]) => pathname === to)
  )
  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="lg:hidden fixed inset-0 z-40 bg-black/60 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      <aside className={`
        fixed left-0 top-0 h-screen bg-black flex flex-col z-50 border-r border-white/10 overflow-y-auto no-scrollbar
        transition-transform duration-200
        w-64
        lg:w-56 lg:translate-x-0
        ${isOpen ? 'translate-x-0' : '-translate-x-full lg:translate-x-0'}
      `}>
        <div className="px-4 py-4 flex-shrink-0 border-b border-white/8">
          <div className="flex items-center justify-between gap-2.5">
            <div className="flex items-center gap-2.5">
              <NavLink to="/" onClick={onClose} className="w-8 h-8 bg-atlas-lime flex items-center justify-center flex-shrink-0" title="Atlas home">
                <span className="text-black text-xs font-display font-extrabold">M</span>
              </NavLink>
              <div>
                <p className="text-atlas-heading text-[13px] font-display font-extrabold leading-none tracking-tight">Music Atlas</p>
                <p className="text-atlas-muted text-[10px] font-body leading-none mt-0.5">taste signals, mapped</p>
              </div>
            </div>
            {/* Close button — mobile only */}
            <button
              onClick={onClose}
              className="lg:hidden w-7 h-7 flex items-center justify-center text-atlas-muted hover:text-atlas-heading"
              aria-label="Close navigation"
            >
              <span className="text-lg leading-none">×</span>
            </button>
          </div>
        </div>

        {ROOM_ORDER.map((roomId, index) => {
          const room = ROOMS[roomId]
          const expanded = roomId === activeRoomId
          return (
            <nav key={roomId} className={`px-1 py-1 ${index > 0 ? 'border-t border-white/5' : ''}`}>
              <SectionLabel to={`/${roomId}`} room={room} expanded={expanded} onClose={onClose} />
              <div
                className={`grid transition-[grid-template-rows] duration-300 ease-out ${
                  expanded ? '[grid-template-rows:1fr]' : '[grid-template-rows:0fr]'
                }`}
              >
                <div className="overflow-hidden min-h-0" inert={!expanded || undefined}>
                  {room.features.map(([label, to, , , icon]) => (
                    <NavItem key={to} to={to} icon={icon} label={label} onClose={onClose} />
                  ))}
                </div>
              </div>
            </nav>
          )
        })}

        <div className="px-4 py-4 mt-auto flex-shrink-0 border-t border-white/5">
          <p className="text-atlas-heading text-xs font-display font-extrabold">1M / 3.62M</p>
          <p className="text-atlas-muted text-[10px] font-body mt-0.5">playlists / tracks</p>
        </div>
      </aside>
    </>
  )
}
