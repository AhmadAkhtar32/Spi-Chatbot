import { motion } from 'framer-motion'

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
 */
export default function AnimatedBackground() {
  return (
    <div className="absolute inset-0 overflow-hidden pointer-events-none" aria-hidden="true">
      <motion.div
        className="absolute -top-24 -left-20 w-[420px] h-[420px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(37,99,235,0.18) 0%, rgba(37,99,235,0) 70%)' }}
        animate={{ x: [0, 480, 120, 0], y: [0, 260, 420, 0] }}
        transition={{ duration: 10, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute top-1/3 -right-24 w-[380px] h-[380px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(96,165,250,0.16) 0%, rgba(96,165,250,0) 70%)' }}
        animate={{ x: [0, -460, -100, 0], y: [0, -220, 300, 0] }}
        transition={{ duration: 12, repeat: Infinity, ease: 'easeInOut' }}
      />
      <motion.div
        className="absolute bottom-[-120px] left-1/3 w-[460px] h-[460px] rounded-full blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(29,78,216,0.14) 0%, rgba(29,78,216,0) 70%)' }}
        animate={{ x: [0, 340, -260, 0], y: [0, -300, -80, 0] }}
        transition={{ duration: 14, repeat: Infinity, ease: 'easeInOut' }}
      />
    </div>
  )
}
