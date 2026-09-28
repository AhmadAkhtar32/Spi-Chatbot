import { useEffect, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'

/**
 * A quiet, ambient motion layer — three large, heavily blurred blue
 * shapes drifting slowly behind the page content. Positioned absolutely
 * with a lower z-index so it never interferes with text or interaction;
 * content should be wrapped in a `relative z-10` container on top of it.
 *
 * Kept intentionally subtle: low opacity, very slow movement, no sharp
 * edges — meant to be felt more than seen, the way it reads on
 * enterprise AI dashboards (watsonx Orchestrate, Copilot) rather than
 * looking like a decorative marketing background.
 *
 * On phones (and for users who prefer reduced motion) the blobs stay
 * still and are smaller — blurred infinite animations are expensive on
 * mobile GPUs and drain battery.
 */
function useIsSmallScreen(breakpoint = 768) {
  const query = `(max-width: ${breakpoint - 1}px)`
  const [small, setSmall] = useState(
    () => typeof window !== 'undefined' && window.matchMedia(query).matches
  )
  useEffect(() => {
    const mq = window.matchMedia(query)
    const onChange = (e) => setSmall(e.matches)
    mq.addEventListener('change', onChange)
    return () => mq.removeEventListener('change', onChange)
  }, [query])
  return small
}

export default function AnimatedBackground() {
  const reduceMotion = useReducedMotion()
  const small = useIsSmallScreen()
  const still = reduceMotion || small

  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      <motion.div
        className="absolute -top-24 -left-20 w-[260px] h-[260px] md:w-[420px] md:h-[420px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(37,99,235,0.18) 0%, rgba(37,99,235,0) 70%)' }}
        animate={still ? undefined : { x: [0, 480, 120, 0], y: [0, 260, 420, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute top-1/3 -right-24 w-[240px] h-[240px] md:w-[380px] md:h-[380px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(96,165,250,0.16) 0%, rgba(96,165,250,0) 70%)' }}
        animate={still ? undefined : { x: [0, -460, -100, 0], y: [0, -220, 300, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute bottom-[-120px] left-1/3 w-[280px] h-[280px] md:w-[460px] md:h-[460px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(29,78,216,0.14) 0%, rgba(29,78,216,0) 70%)' }}
        animate={still ? undefined : { x: [0, 340, -260, 0], y: [0, -300, -80, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}