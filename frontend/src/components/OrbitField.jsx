import { useEffect, useRef } from 'react'
import * as d3 from 'd3'

/**
 * Radial orbit chart: one subject at the center, neighbors placed by
 * co-occurrence strength (stronger = closer, larger, more opaque).
 * Strength is the only encoding — a single accent hue keeps color honest.
 *
 * Props:
 *   center     string — subject label
 *   neighbors  [{ title, strength }] with strength in [0, 1]
 *   accent     hex color for the whole field
 *   selected   currently selected neighbor (highlighted)
 *   onSelect   (neighbor) => void
 */
export default function OrbitField({ center, neighbors = [], accent = '#C084FC', selected, onSelect }) {
  const svgRef = useRef(null)

  useEffect(() => {
    const el = svgRef.current
    if (!el || !neighbors.length) return

    const draw = () => {
      const width = Math.max(320, el.getBoundingClientRect().width)
      const height = Math.min(620, Math.max(420, width * 0.64))
      const cx = width * 0.52
      const cy = height * 0.50
      el.setAttribute('height', height)

      const svg = d3.select(el)
      svg.selectAll('*').remove()

      svg.append('line').attr('x1', cx).attr('y1', 24).attr('x2', cx).attr('y2', height - 24)
        .attr('stroke', 'rgba(243,240,232,0.12)')
      svg.append('line').attr('x1', 24).attr('y1', cy).attr('x2', width - 24).attr('y2', cy)
        .attr('stroke', 'rgba(243,240,232,0.12)')

      ;[0.22, 0.38, 0.54, 0.70].forEach(r => {
        svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', r * Math.min(width, height) / 2)
          .attr('fill', 'none').attr('stroke', 'rgba(243,240,232,0.1)').attr('stroke-width', 1)
      })

      neighbors.forEach((n, i) => {
        const angle = (i / neighbors.length) * 2 * Math.PI - Math.PI / 2
        const radius = (0.24 + (1 - n.strength) * 0.52) * Math.min(width, height) / 2
        const nx = cx + Math.cos(angle) * radius
        const ny = cy + Math.sin(angle) * radius
        const isSelected = selected && selected.title === n.title

        svg.append('line').attr('x1', cx).attr('y1', cy).attr('x2', nx).attr('y2', ny)
          .attr('stroke', accent).attr('stroke-width', 1)
          .attr('opacity', 0.12 + n.strength * 0.24)

        const g = svg.append('g').attr('transform', `translate(${nx},${ny})`)
          .style('cursor', 'pointer')
          .on('click', () => onSelect?.(n))

        const r = 5 + n.strength * 8
        g.append('circle').attr('r', r).attr('fill', accent)
          .attr('opacity', 0.45 + n.strength * 0.5)
        g.append('circle').attr('r', r + 8).attr('fill', 'none')
          .attr('stroke', isSelected ? '#f7f3ea' : accent)
          .attr('opacity', isSelected ? 0.9 : 0.22)

        if (n.strength > 0.56 || isSelected) {
          g.append('text').attr('x', 0).attr('y', -(r + 10)).attr('text-anchor', 'middle')
            .attr('fill', '#e5e2e1').attr('font-size', '11px').attr('font-family', 'JetBrains Mono')
            .text(n.title.length > 16 ? `${n.title.slice(0, 15)}...` : n.title)
        }
      })

      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 43)
        .attr('fill', accent).attr('fill-opacity', 0.11)
        .attr('stroke', accent).attr('stroke-width', 2)
      svg.append('circle').attr('cx', cx).attr('cy', cy).attr('r', 29)
        .attr('fill', '#101010').attr('stroke', 'rgba(243,240,232,0.4)').attr('stroke-width', 1)
      svg.append('text').attr('x', cx).attr('y', cy - 2).attr('text-anchor', 'middle')
        .attr('fill', '#f7f3ea').attr('font-size', '13px').attr('font-family', 'Archivo Narrow').attr('font-weight', '800')
        .text(center.length > 15 ? `${center.slice(0, 14)}...` : center)
      svg.append('text').attr('x', cx).attr('y', cy + 13).attr('text-anchor', 'middle')
        .attr('fill', accent).attr('font-size', '9px').attr('font-family', 'JetBrains Mono')
        .text('subject')
    }

    draw()
    const observer = new ResizeObserver(draw)
    observer.observe(el.parentElement)
    return () => observer.disconnect()
  }, [center, neighbors, accent, selected, onSelect])

  return (
    <svg
      ref={svgRef}
      className="w-full"
      role="img"
      aria-label={`Orbit chart: ${neighbors.length} artists placed around ${center} by playlist co-occurrence strength`}
    />
  )
}
