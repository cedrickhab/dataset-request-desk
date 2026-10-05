/**
 * Amber particle-wave artwork for the login's branding panel.
 *
 * Several curved ribbons sweep across the lower portion of the panel: each is
 * a layered pair of sine waves with its own phase, amplitude and depth, and
 * particles are sampled along and across them with a seeded generator, so the
 * composition is identical on every load. A brighter crest of closely spaced
 * particles rides selected ribbons; a few large, softly blurred points sit in
 * the foreground; broad low-opacity radial glows sit behind everything. Dark
 * space stays between the ribbons and the artwork fades upward into the panel.
 *
 * Rendering is static (drawn once per resize) — preferred over animation
 * unless motion materially improves the match, and cheaper on battery. The
 * canvas is aria-hidden decoration: it never intercepts pointers and never
 * enters the accessibility tree. Device pixel ratio is accounted for, capped
 * at 2 so 4K panels do not quadruple the fill cost.
 */

import { useEffect, useRef } from 'react'

/** Deterministic PRNG so the artwork does not reshuffle on every render. */
function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a |= 0
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

interface Ribbon {
  baseY: number // fraction of height at x=0
  rise: number // downward drift across the width, fraction of height
  amp1: number
  freq1: number
  phase1: number
  amp2: number
  freq2: number
  phase2: number
  thickness: number // jitter spread, fraction of height
  depth: number // 0 = far, 1 = near
  crest: boolean
}

const AMBER = { r: 255, g: 188, b: 66 }
const GOLD = { r: 255, g: 214, b: 130 }

function mixColour(t: number, alpha: number): string {
  const c = {
    r: Math.round(AMBER.r + (GOLD.r - AMBER.r) * t),
    g: Math.round(AMBER.g + (GOLD.g - AMBER.g) * t),
    b: Math.round(AMBER.b + (GOLD.b - AMBER.b) * t),
  }
  return `rgba(${c.r},${c.g},${c.b},${alpha.toFixed(3)})`
}

function ribbonY(ribbon: Ribbon, x: number, width: number, height: number): number {
  const t = x / width
  return (
    (ribbon.baseY + ribbon.rise * t) * height +
    ribbon.amp1 * height * Math.sin(t * ribbon.freq1 + ribbon.phase1) +
    ribbon.amp2 * height * Math.sin(t * ribbon.freq2 + ribbon.phase2)
  )
}

export function LoginParticleWave({ className }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const context = canvas.getContext('2d')
    if (!context) return
    const ctx = context

    const DPR_CAP = 2

    function draw(width: number, height: number) {
      const dpr = Math.min(window.devicePixelRatio || 1, DPR_CAP)
      canvas!.width = Math.max(1, Math.round(width * dpr))
      canvas!.height = Math.max(1, Math.round(height * dpr))
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
      ctx.clearRect(0, 0, width, height)

      const random = mulberry32(0x5eedBEEF)

      // --- broad, restrained glows behind everything ---
      for (let i = 0; i < 4; i += 1) {
        const gx = width * (0.15 + random() * 0.7)
        const gy = height * (0.35 + random() * 0.55)
        const gr = Math.min(width, height) * (0.28 + random() * 0.3)
        const glow = ctx.createRadialGradient(gx, gy, 0, gx, gy, gr)
        glow.addColorStop(0, `rgba(255,180,60,${(0.05 + random() * 0.05).toFixed(3)})`)
        glow.addColorStop(1, 'rgba(255,180,60,0)')
        ctx.fillStyle = glow
        ctx.fillRect(0, 0, width, height)
      }

      // --- ribbons: far and shallow first, near and bold last ---
      const RIBBONS = 7
      const ribbons: Ribbon[] = []
      for (let i = 0; i < RIBBONS; i += 1) {
        const depth = i / (RIBBONS - 1)
        ribbons.push({
          baseY: 0.18 + 0.62 * depth + (random() - 0.5) * 0.06,
          rise: 0.05 + random() * 0.14,
          amp1: 0.05 + random() * 0.09,
          freq1: 4 + random() * 3.5,
          phase1: random() * Math.PI * 2,
          amp2: 0.015 + random() * 0.035,
          freq2: 9 + random() * 6,
          phase2: random() * Math.PI * 2,
          thickness: 0.02 + depth * 0.05,
          depth,
          crest: depth > 0.55 && depth < 0.95,
        })
      }

      // --- particles along and across each ribbon ---
      for (const ribbon of ribbons) {
        const perRibbon = Math.round(140 + ribbon.depth * 240)
        for (let p = 0; p < perRibbon; p += 1) {
          const x = random() * width
          // Fade particles out toward the very top so the artwork dissolves
          // into the panel instead of ending abruptly.
          const spread = ribbon.thickness * height
          const offset = (random() + random() - 1) * spread // triangular, denser on the spine
          const y = ribbonY(ribbon, x, width, height) + offset
          const offSpine = Math.abs(offset) / Math.max(spread, 1)
          const fadeTop = Math.min(1, Math.max(0, y / (height * 0.28)))
          const alpha = (0.12 + 0.5 * ribbon.depth) * (1 - offSpine * 0.75) * fadeTop
          if (alpha < 0.02) continue
          const radius = 0.4 + ribbon.depth * 1.1 + random() * 0.7
          ctx.fillStyle = mixColour(random(), alpha)
          ctx.beginPath()
          ctx.arc(x, y, radius, 0, Math.PI * 2)
          ctx.fill()
        }

        // --- brighter crest of closely spaced particles ---
        if (ribbon.crest) {
          const step = 2.2
          for (let x = 0; x < width; x += step) {
            const y = ribbonY(ribbon, x, width, height)
            const fadeTop = Math.min(1, Math.max(0, y / (height * 0.28)))
            const shimmer = 0.35 + 0.65 * Math.abs(Math.sin(x * 0.011 + ribbon.phase1))
            ctx.fillStyle = mixColour(0.75, 0.75 * shimmer * fadeTop)
            ctx.beginPath()
            ctx.arc(x + (random() - 0.5), y + (random() - 0.5) * 1.6, 0.7 + random() * 0.7, 0, Math.PI * 2)
            ctx.fill()
          }
        }
      }

      // --- smaller sharp points scattered in the dark space between ---
      const strays = Math.round(width / 6)
      for (let i = 0; i < strays; i += 1) {
        const x = random() * width
        const y = height * (0.1 + random() * 0.9)
        const fadeTop = Math.min(1, Math.max(0, y / (height * 0.3)))
        ctx.fillStyle = mixColour(random(), (0.1 + random() * 0.4) * fadeTop)
        ctx.beginPath()
        ctx.arc(x, y, 0.4 + random() * 0.9, 0, Math.PI * 2)
        ctx.fill()
      }

      // --- a few large, softly blurred foreground particles ---
      const blurred = Math.round(width / 55)
      ctx.save()
      ctx.filter = 'blur(3px)'
      for (let i = 0; i < blurred; i += 1) {
        const x = random() * width
        const y = height * (0.45 + random() * 0.55)
        const radius = 2.5 + random() * 4.5
        const glow = ctx.createRadialGradient(x, y, 0, x, y, radius)
        const warm = mixColour(0.5, 0.28 + random() * 0.2)
        glow.addColorStop(0, warm)
        glow.addColorStop(1, 'rgba(255,188,66,0)')
        ctx.fillStyle = glow
        ctx.beginPath()
        ctx.arc(x, y, radius, 0, Math.PI * 2)
        ctx.fill()
      }
      ctx.restore()
    }

    function resize() {
      // The canvas's own CSS box (.story-art: absolute, lower band of the
      // panel) is what the drawing must fill — not the parent panel.
      const rect = canvas!.getBoundingClientRect()
      draw(rect.width, rect.height)
    }

    const observer = new ResizeObserver(resize)
    observer.observe(canvas)
    resize()

    return () => {
      observer.disconnect()
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      className={className}
      aria-hidden="true"
      // Decoration only: it must never swallow a click meant for the form
      // behind it or appear to assistive technology as an image without data.
      style={{ pointerEvents: 'none' }}
    />
  )
}
