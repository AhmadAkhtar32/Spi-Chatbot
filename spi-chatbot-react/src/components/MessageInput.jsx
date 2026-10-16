import { useEffect, useRef, useState } from 'react'
import {
  Send,
  Paperclip,
  Mic,
  Square,
  Loader2,
  X,
} from 'lucide-react'
import { API_BASE } from '../api.js'

const MAX_CHARS = 2000

export default function MessageInput({
  onSend,
  disabled,
  value,
  onValueChange,
  onClear,
  hasMessages,
  inputPlaceholder,
  voiceEnabled = true,
}) {
  const [internalValue, setInternalValue] = useState('')
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [voiceError, setVoiceError] = useState(null)

  const textareaRef = useRef(null)
  const mediaRecorderRef = useRef(null)
  const audioChunksRef = useRef([])

  const text = value !== undefined ? value : internalValue
  const setText =
    onValueChange !== undefined ? onValueChange : setInternalValue

  useEffect(() => {
    const element = textareaRef.current

    if (!element) return

    element.style.height = 'auto'
    element.style.height =
      Math.min(element.scrollHeight, 160) + 'px'
  }, [text])

  function submit(event) {
    event?.preventDefault()

    const trimmed = text.trim()

    if (!trimmed || disabled) return

    onSend(trimmed)
    setText('')
  }

  function handleKeyDown(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      submit()
    }
  }

  async function toggleRecording() {
    if (!voiceEnabled) return

    setVoiceError(null)

    if (isRecording) {
      mediaRecorderRef.current?.stop()
      setIsRecording(false)
      return
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: true,
      })

      const mimeType = MediaRecorder.isTypeSupported('audio/webm')
        ? 'audio/webm'
        : 'audio/mp4'

      const recorder = new MediaRecorder(stream, { mimeType })

      mediaRecorderRef.current = recorder
      audioChunksRef.current = []

      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data)
        }
      }

      recorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop())

        const blob = new Blob(audioChunksRef.current, {
          type: mimeType,
        })

        await sendForTranscription(blob, mimeType)
      }

      recorder.start()
      setIsRecording(true)
    } catch {
      setVoiceError(
        'Microphone access was denied or is unavailable.'
      )
    }
  }

  async function sendForTranscription(blob, mimeType) {
    setIsTranscribing(true)

    try {
      const formData = new FormData()
      const extension = mimeType.includes('webm') ? 'webm' : 'm4a'

      formData.append(
        'file',
        blob,
        `recording.${extension}`
      )

      const response = await fetch(`${API_BASE}/api/transcribe`, {
        method: 'POST',
        body: formData,
      })

      if (!response.ok) {
        const error = await response.json().catch(() => ({}))

        throw new Error(
          error.detail || 'Transcription failed'
        )
      }

      const data = await response.json()

      if (data.transcript) {
        setText(
          text
            ? `${text} ${data.transcript}`
            : data.transcript
        )
      }
    } catch (error) {
      setVoiceError(error.message)
    } finally {
      setIsTranscribing(false)
    }
  }

  return (
    <form
      onSubmit={submit}
      className="shrink-0 border-t border-border bg-surface px-6 py-3.5"
    >
      <div className="max-w-3xl mx-auto">
        <div className="flex items-end gap-2">
          <button
            type="button"
            disabled
            title="Attachments coming soon"
            className="
              h-10 w-10 shrink-0 rounded-md
              border border-border bg-bg
              flex items-center justify-center
              text-ink-secondary/50
              cursor-not-allowed mb-[3px]
            "
          >
            <Paperclip
              className="w-4 h-4"
              strokeWidth={2}
            />
          </button>

          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              rows={1}
              value={text}
              maxLength={MAX_CHARS}
              onChange={(event) =>
                setText(event.target.value)
              }
              onKeyDown={handleKeyDown}
              placeholder={
                isRecording
                  ? 'Listening... (English or Urdu)'
                  : isTranscribing
                    ? 'Transcribing...'
                    : inputPlaceholder ||
                      'Type your question...'
              }
              disabled={isTranscribing}
              className="
                w-full resize-none px-4 py-2.5
                rounded-md border border-border
                bg-bg text-[14px] text-ink
                placeholder:text-ink-secondary/60
                focus:outline-none
                focus:border-primary
                focus:bg-surface
                transition-colors leading-relaxed
                disabled:opacity-60
              "
              style={{
                minHeight: '40px',
                maxHeight: '160px',
              }}
            />
          </div>

          <button
            type="button"
            onClick={toggleRecording}
            disabled={isTranscribing || !voiceEnabled}
            title={
              !voiceEnabled
                ? 'Voice is unavailable in the role demo'
                : isRecording
                  ? 'Stop recording'
                  : 'Speak in English or Urdu'
            }
            className={`
              h-10 w-10 shrink-0 rounded-md
              border flex items-center justify-center
              transition-colors mb-[3px]
              ${
                isRecording
                  ? 'border-danger bg-danger/10 text-danger animate-pulse'
                  : 'border-border bg-bg text-ink-secondary hover:text-primary hover:border-primary/40'
              }
              disabled:opacity-50
              disabled:cursor-not-allowed
            `}
          >
            {isTranscribing ? (
              <Loader2
                className="w-4 h-4 animate-spin"
                strokeWidth={2}
              />
            ) : isRecording ? (
              <Square
                className="w-3.5 h-3.5 fill-current"
                strokeWidth={2}
              />
            ) : (
              <Mic
                className="w-4 h-4"
                strokeWidth={2}
              />
            )}
          </button>

          <button
            type="submit"
            disabled={disabled || !text.trim()}
            className="
              h-10 w-10 shrink-0 rounded-md
              bg-primary flex items-center
              justify-center mb-[3px]
              hover:bg-primary-dark
              transition-colors
              disabled:opacity-40
              disabled:cursor-not-allowed
              focus:outline-none
              focus-visible:ring-2
              focus-visible:ring-primary/40
            "
            aria-label="Send message"
          >
            <Send
              className="w-4 h-4 text-white"
              strokeWidth={2}
            />
          </button>
        </div>

        <div className="flex items-center justify-between mt-1.5 px-1">
          <div className="flex items-center gap-3">
            {voiceError ? (
              <span className="text-[11px] text-danger">
                {voiceError}
              </span>
            ) : (
              <span className="text-[11px] text-ink-secondary/70">
                Enter to send &middot; Shift+Enter for new line
                {voiceEnabled && (
                  <> &middot; Mic supports Urdu</>
                )}
              </span>
            )}

            {hasMessages && onClear && (
              <button
                type="button"
                onClick={onClear}
                className="
                  flex items-center gap-1
                  text-[11px]
                  text-ink-secondary/70
                  hover:text-danger
                  transition-colors
                "
              >
                <X className="w-3 h-3" />
                Clear conversation
              </button>
            )}
          </div>

          <span className="text-[11px] text-ink-secondary/50 tabular-nums">
            {text.length}/{MAX_CHARS}
          </span>
        </div>
      </div>
    </form>
  )
}