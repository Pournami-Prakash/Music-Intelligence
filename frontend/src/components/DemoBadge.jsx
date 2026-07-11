export default function DemoBadge({ detail }) {
  return (
    <div className="flex items-center gap-1.5 px-3 py-1.5 bg-atlas-surface border border-atlas-amber/25 w-fit">
      <span className="w-1.5 h-1.5 rounded-full bg-atlas-amber flex-shrink-0" />
      <span className="text-atlas-amber text-[10px] font-display font-bold uppercase tracking-widest">
        demo data — {detail || 'real results load once compute finishes'}
      </span>
    </div>
  )
}
