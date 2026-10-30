import { useEffect, useRef, useState } from 'react'
import { ArrowUp, Paperclip, Mic, Square, Loader2, X } from 'lucide-react'
import { API_BASE } from '../api/client.js'

export default function MessageInput({
  onSend, disabled, value, onValueChange, onClear, hasMessages, inputPlaceholder,
  imageEnabled = false,
  voiceEnabled = false, voiceContext = null, onVoiceSessionExpired,
  showAttachments = true, showVoiceControl = true, maxChars = 2000,
}) {
  const [internalValue, setInternalValue] = useState('')
  const [phase, setPhase] = useState('idle')
  const [seconds, setSeconds] = useState(0)
  const [voiceError, setVoiceError] = useState('')
  const [voiceNotice, setVoiceNotice] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [imagePreview, setImagePreview] = useState('')
  const imagePicker = useRef(null)
  const imageSending = useRef(false)
  const textarea = useRef(null)
  const waveform = useRef(null)
  const composer = useRef(null)
  const voice = useRef({ active: true, ticket: 0, phase: 'idle' })
  const text = value !== undefined ? value : internalValue
  const setText = onValueChange || setInternalValue
  const latestText = useRef(text)
  latestText.current = text
  const busy = phase !== 'idle'

  useEffect(() => {
    if (!textarea.current) return
    textarea.current.style.height = 'auto'
    textarea.current.style.height = Math.min(textarea.current.scrollHeight, 160) + 'px'
  }, [text, phase])

  useEffect(() => {
    if (phase === 'starting' || phase === 'recording') composer.current?.focus()
    if (phase === 'idle' && !disabled) textarea.current?.focus()
  }, [phase, disabled])

  useEffect(() => {
    if (!imageFile) { setImagePreview(''); return }
    const url = URL.createObjectURL(imageFile)
    setImagePreview(url)
    return () => URL.revokeObjectURL(url)
  }, [imageFile])

  function chooseImage(event) {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file || busy || disabled || !imageEnabled) return
    setVoiceError('')
    setVoiceNotice('')
    if (!['image/png', 'image/jpeg'].includes(file.type) || !file.size || file.size > 2 * 1024 * 1024) {
      setVoiceError('Choose one PNG or JPEG screenshot, up to 2 MiB.')
      return
    }
    setImageFile(file)
  }

  async function dispatchQuestion(question) {
    if (imageSending.current) return
    if (!imageFile) { onSend(question); setText(''); return }
    imageSending.current = true
    const selected = imageFile
    try {
      const sent = await onSend(question, null, selected)
      if (!voice.current.active) return
      if (sent === false) {
        setText(question)
        setVoiceError('Screenshot request failed. Your image and question are kept for retry.')
      } else {
        setImageFile(current => current === selected ? null : current)
        setText('')
      }
    } finally { imageSending.current = false }
  }

  function recordingKey(event) {
    if (event.nativeEvent?.isComposing || event.repeat) return
    if (event.key === 'Escape' && busy) {
      event.preventDefault()
      cancelVoice()
    } else if (event.key === 'Enter' && !event.shiftKey && busy) {
      event.preventDefault()
      if (phase === 'recording') submit()
    }
  }

  function releaseCapture(work) {
    clearTimeout(work.limit)
    clearInterval(work.ticker)
    cancelAnimationFrame(work.frame)
    work.source?.disconnect()
    work.source = null
    work.analyser = null
    work.audio?.close().catch(() => {})
    work.audio = null
    work.stream?.getTracks().forEach(track => track.stop())
    work.stream = null
  }

  function discard(work) {
    work.ticket += 1
    work.request?.abort()
    work.request = null
    if (work.recorder) {
      work.recorder.onstop = null
      work.recorder.ondataavailable = null
      if (work.recorder.state !== 'inactive') work.recorder.stop()
    }
    work.recorder = null
    releaseCapture(work)
    work.phase = 'idle'
  }

  useEffect(() => {
    const work = voice.current
    work.active = true
    return () => {
      work.active = false
      discard(work)
    }
  }, [])

  function cancelVoice() {
    discard(voice.current)
    setPhase('idle')
    setVoiceError('')
    setVoiceNotice('Recording cancelled.')
  }

  function finishRecording(sendNow = false) {
    const work = voice.current
    if (work.phase !== 'recording' || work.recorder?.state !== 'recording') return
    work.sendNow = sendNow
    work.phase = 'transcribing'
    setPhase('transcribing')
    work.recorder.stop()
  }

  async function startRecording() {
    const work = voice.current
    if (work.phase === 'recording') return finishRecording(false)
    if (disabled || !voiceEnabled || work.phase !== 'idle' || !voiceContext?.token) return

    setVoiceError('')
    setVoiceNotice('')

    if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      setVoiceError('Microphone input needs HTTPS or localhost and a supported browser.')
      return
    }

    const ticket = ++work.ticket
    const current = () => work.active && work.ticket === ticket
    work.phase = 'starting'
    setPhase('starting')

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      if (!current()) {
        stream.getTracks().forEach(track => track.stop())
        return
      }

      work.stream = stream
      const type = ['audio/webm;codecs=opus', 'audio/webm', 'audio/mp4', 'audio/ogg;codecs=opus']
        .find(candidate => MediaRecorder.isTypeSupported(candidate))

      if (!type) throw new Error('This browser cannot record a supported audio format.')

      const recorder = new MediaRecorder(stream, { mimeType: type })
      work.recorder = recorder
      work.sendNow = false
      let bytes = 0
      const chunks = []

      recorder.ondataavailable = event => {
        bytes += event.data.size
        if (bytes <= 4 * 1024 * 1024) chunks.push(event.data)
        else if (recorder.state === 'recording') recorder.stop()
      }

      recorder.onstop = async () => {
        releaseCapture(work)
        work.recorder = null
        if (!current()) return

        if (bytes > 4 * 1024 * 1024) {
          work.phase = 'idle'
          setPhase('idle')
          setVoiceError('Recording is too large. Please record a shorter question.')
          return
        }

        await transcribe(
          new Blob(chunks, { type }),
          type,
          ticket,
          work.sendNow
        )
      }

      recorder.onerror = () => {
        if (!current()) return
        discard(work)
        setPhase('idle')
        setVoiceError('Recording failed. Please try again.')
      }

      try {
        const Audio = window.AudioContext || window.webkitAudioContext
        if (Audio) {
          work.audio = new Audio()
          work.audio.resume().catch(() => {})
          work.analyser = work.audio.createAnalyser()
          work.analyser.fftSize = 256
          work.source = work.audio.createMediaStreamSource(stream)
          work.source.connect(work.analyser)
        }
      } catch {
        work.analyser = null
      }

      recorder.start(1000)
      work.phase = 'recording'
      setPhase('recording')
      setSeconds(0)

      const started = Date.now()
      work.ticker = setInterval(() => {
        if (current()) {
          setSeconds(Math.min(60, Math.floor((Date.now() - started) / 1000)))
        }
      }, 250)

      work.limit = setTimeout(() => {
        if (current()) finishRecording(false)
      }, 60000)

      const levels = Array(180).fill(3)
      let sampledAt = 0
      function draw() {
        if (!current() || work.phase !== 'recording') return
        const canvas = waveform.current
        const painter = canvas?.getContext('2d')
        if (painter) {
          const width = Math.max(1, Math.floor(canvas.getBoundingClientRect().width))
          const ratio = Math.min(window.devicePixelRatio || 1, 2)
          if (canvas.width !== Math.round(width * ratio) || canvas.height !== Math.round(32 * ratio)) {
            canvas.width = Math.round(width * ratio)
            canvas.height = Math.round(32 * ratio)
          }
          if (Date.now() - sampledAt >= 40) {
            sampledAt = Date.now()
            const samples = new Uint8Array(work.analyser?.fftSize || 256)
            samples.fill(128)
            work.analyser?.getByteTimeDomainData(samples)
            const energy = samples.reduce((sum, value) => sum + ((value - 128) / 128) ** 2, 0) / samples.length
            const decibels = 20 * Math.log10(Math.max(Math.sqrt(energy), 0.00001))
            const strength = Math.max(0, Math.min(1, (decibels + 65) / 47))
            levels.push(3 + strength * 23)
            levels.shift()
          }
          painter.setTransform(ratio, 0, 0, ratio, 0, 0)
          painter.clearRect(0, 0, width, 32)
          painter.strokeStyle = getComputedStyle(canvas).color
          painter.lineWidth = 2
          painter.lineCap = 'round'
          const count = Math.min(levels.length, Math.floor(width / 5))
          levels.slice(-count).forEach((height, bar) => {
            painter.globalAlpha = height > 5 ? 0.9 : 0.35
            painter.beginPath()
            painter.moveTo(bar * 5 + 2, 16 - (height - 2) / 2)
            painter.lineTo(bar * 5 + 2, 16 + (height - 2) / 2)
            painter.stroke()
          })
          painter.globalAlpha = 1
        }
        work.frame = requestAnimationFrame(draw)
      }
      work.frame = requestAnimationFrame(draw)
    } catch (error) {
      if (!current()) return
      discard(work)
      setPhase('idle')
      setVoiceError(
        error.name === 'NotAllowedError'
          ? 'Microphone permission was denied. Allow it in your browser settings.'
          : error.message || 'Microphone is unavailable.'
      )
    }
  }

  async function transcribe(blob, mediaType, ticket, sendNow) {
    const work = voice.current
    const current = () => work.active && work.ticket === ticket

    if (!current()) return
    if (!blob.size) {
      work.phase = 'idle'
      setPhase('idle')
      setVoiceError('No audio was captured. Please try again.')
      return
    }

    work.phase = 'transcribing'
    setPhase('transcribing')

    const controller = new AbortController()
    work.request = controller
    let timedOut = false
    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 65000)

    try {
      const query = new URLSearchParams({
        expert: voiceContext.expert,
        module: voiceContext.module,
      })

      const response = await fetch(`${API_BASE}/api/v1/experts/transcribe?${query}`, {
        method: 'POST',
        cache: 'no-store',
        signal: controller.signal,
        headers: {
          Authorization: `Bearer ${voiceContext.token}`,
          'Content-Type': mediaType,
        },
        body: blob,
      })

      if (!current() || controller.signal.aborted) return

      if (response.status === 401) {
        onVoiceSessionExpired?.('Session expired. Please open the assistant again.')
        throw new Error('Session expired. Please open the assistant again.')
      }

      if (response.status === 403) {
        throw new Error('Voice input is not permitted for this expert or module.')
      }

      const data = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Voice input failed.')
      }

      if (typeof data.transcript !== 'string' || !data.transcript.trim()) {
        throw new Error('No speech was detected.')
      }

      const merged = [
        latestText.current.trim(),
        data.transcript.trim(),
      ].filter(Boolean).join(' ')

      if (merged.length > maxChars) {
        throw new Error('Your question is too long. Please record a shorter question.')
      }

      if (!current() || controller.signal.aborted) return

      work.phase = 'idle'
      setPhase('idle')
      setVoiceNotice(data.corrected === true ? 'ERP spelling adjusted from context.' : '')

      if (sendNow) { await dispatchQuestion(merged) } else {
        setText(merged)
      }
    } catch (error) {
      if (current()) {
        setVoiceError(
          timedOut
            ? 'Transcription timed out. Please try a shorter recording.'
            : error.message || 'Voice input failed.'
        )
      }
    } finally {
      clearTimeout(timeout)
      if (current()) {
        work.request = null
        work.phase = 'idle'
        setPhase('idle')
      }
    }
  }

  function submit(event) {
    event?.preventDefault()
    if (disabled) return
    if (phase === 'recording') return finishRecording(true)
    if (phase !== 'idle' || (!text.trim() && !imageFile)) return
    dispatchQuestion(text.trim() || 'Explain this ERP screen or error in English.')
  }

  return (
    <form ref={composer} tabIndex={-1} onKeyDown={recordingKey} onSubmit={submit}
      className="shrink-0 border-t border-border bg-surface px-4 sm:px-6 py-3 outline-none">
      <div className="max-w-3xl mx-auto">
        {imageFile && <div className="mb-2 flex items-center gap-3 rounded-xl border border-border bg-bg p-2">
          <img src={imagePreview || undefined} alt="Selected screenshot" className="h-14 w-14 rounded-lg border border-border object-cover"
            onError={() => { setImageFile(null); setVoiceError('The screenshot could not be opened. Choose another PNG or JPEG.') }} />
          <div className="min-w-0 flex-1 text-xs text-ink-secondary">
            <p className="font-medium text-ink">Screenshot attached</p>
            <p>{Math.ceil(imageFile.size / 1024)} KB · sent only when you press Send</p>
          </div>
          <button type="button" onClick={() => setImageFile(null)} disabled={busy || disabled}
            aria-label="Remove screenshot" className="p-2 text-ink-secondary hover:text-danger disabled:opacity-40"><X className="h-4 w-4" /></button>
        </div>}
        <input ref={imagePicker} type="file" accept="image/png,image/jpeg" onChange={chooseImage} className="hidden" aria-label="Choose screenshot file" />
        <div data-spia-input-row data-recording={busy ? 'true' : 'false'}>
          {busy && <button data-spia-voice-cancel type="button" onClick={cancelVoice}
            aria-label="Cancel voice input" title="Cancel voice input (Esc)">
            <X className="h-5 w-5" />
          </button>}
          {!busy && (imageEnabled || showAttachments) && <button data-spia-attachment type="button" style={{ order: -1 }} disabled={!imageEnabled || disabled}
            onClick={() => imagePicker.current?.click()}
            title="Attach one PNG or JPEG screenshot, up to 2 MiB" aria-label="Attach screenshot">
            <Paperclip className="h-5 w-5" />
          </button>}
          <div data-spia-editor>
            {busy ? (
              <div data-voice-state={phase}>
                {phase === 'recording'
                  ? <canvas ref={waveform} width="240" height="32" aria-hidden="true" />
                  : <span className="flex items-center justify-center gap-2 text-sm text-ink-secondary">
                      <Loader2 className="h-4 w-4 animate-spin" />
                      {phase === 'starting' ? 'Allow microphone access' : 'Transcribing...'}
                    </span>}
              </div>
            ) : (
              <textarea ref={textarea} rows={1} dir="auto" value={text} maxLength={maxChars}
                onChange={event => setText(event.target.value)}
                onKeyDown={event => {
                  if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && !event.repeat) {
                    event.preventDefault(); submit()
                  }
                }}
                placeholder={inputPlaceholder || 'Type your question...'} disabled={disabled}
                style={{ fontFamily: /[\u0600-\u06ff]/.test(text) ? '"Noto Naskh Arabic", "Segoe UI", Tahoma, Arial, sans-serif' : undefined }} />
            )}
          </div>
          {showVoiceControl && <button data-spia-mic type="button" onClick={startRecording}
            disabled={!voiceEnabled || phase === 'starting' || phase === 'transcribing' || disabled}
            aria-label={phase === 'recording' ? 'Stop and review recording' : 'Start voice input'}
            title={phase === 'recording' ? 'Stop and review recording' : 'Record in English or Urdu; audio is sent to Groq'}>
            {phase === 'recording' ? <Square className="h-3.5 w-3.5 fill-current" /> : <Mic className="h-5 w-5" />}
          </button>}
          <button data-spia-send type="submit"
            disabled={disabled || (phase !== 'recording' && (busy || (!text.trim() && !imageFile)))}
            aria-label={phase === 'recording' ? 'Send voice question' : 'Send message'}
            title={phase === 'recording' ? 'Finish recording and send the question' : 'Send message'}>
            {phase === 'transcribing' ? <Loader2 className="h-4 w-4 animate-spin" /> : <ArrowUp className="h-5 w-5" />}
          </button>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-1 mt-2 px-2">
          <span role={busy ? 'status' : undefined} className={`flex items-center gap-1.5 text-xs ${voiceError ? 'text-danger' : 'text-ink-secondary'}`}>
            {phase === 'recording' && <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />}
            {voiceError || voiceNotice || (phase === 'recording'
              ? `Recording ${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} - Enter to send`
              : phase === 'transcribing' ? 'Transcribing your recording...'
              : phase === 'starting' ? 'Waiting for microphone permission...'
              : 'Enter to send; Shift+Enter for new line')}
          </span>
          {busy ? <span className="text-xs text-ink-secondary">Esc to cancel</span>
            : <div className="flex items-center gap-3 text-[11px] text-ink-secondary/70">
                {hasMessages && onClear && <button type="button" onClick={onClear} className="hover:text-danger">Clear conversation</button>}
                <span className="tabular-nums">{text.length}/{maxChars}</span>
              </div>}
        </div>
      </div>
    </form>
  )
}
