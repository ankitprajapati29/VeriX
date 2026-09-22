import { useRef, useState } from 'react'
import type { ReactNode, DragEvent } from 'react'

type AadhaarValidation = {
  number_found: boolean
  masked_number?: string
  format_valid: boolean
  verhoeff_valid: boolean
  status: string
}

type ValidationResult = {
  number_found?: boolean
  format_valid?: boolean
  verhoeff_valid?: boolean
  fourth_character?: string
  fourth_character_valid?: boolean
  checksum_valid?: boolean
  status?: string
  gstin?: string
  epic?: string
  number?: string
  mrz?: {
    detected?: boolean
    valid?: boolean
    validation_count?: number
    validations?: Record<string, boolean>
  }
  aadhaar?: AadhaarValidation
}

type ForensicsResult = {
  metadata?: {
    present?: boolean
    fields?: Record<string, string>
  }
  ela?: {
    available?: boolean
    max_difference?: number
    mean_difference?: number
    suspicious?: boolean
  }
  qr?: {
    detected?: boolean
    decoded?: boolean
    data?: string | null
  }
  consistency?: {
    consistent?: boolean
    mismatches?: string[]
  }
}

type RiskSignal = {
  signal: string
  points: number
  severity: string
  reason?: string
}

type VerificationResult = {
  document: {
    filename: string
    extension: string
    file_type: string
    size_bytes: number
    sha256: string
  }

  document_type: {
    detected: string
  }

  ocr: {
    text: string
    text_length: number
    confidence: number
  }

  validation: ValidationResult

  forensics: ForensicsResult

  image_quality: {
    width: number
    height: number
    blur_score: number
    brightness: number
    issues: string[]
  }

  consistency: {
    consistent: boolean
    mismatches: string[]
  }

  risk_assessment: {
    score: number | null
    level: string
    signals: RiskSignal[]
    technical_assessment?: string
    disclaimer?: string
  }
}

function Verification() {
  const fileInputRef = useRef<HTMLInputElement>(null)

  const [file, setFile] = useState<File | null>(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<VerificationResult | null>(null)
  const [isDragging, setIsDragging] = useState(false)

  const handleFileChange = (selectedFile?: File) => {
    if (!selectedFile) return

    const allowedTypes = [
      'application/pdf',
      'image/jpeg',
      'image/png',
      'image/webp',
    ]

    if (!allowedTypes.includes(selectedFile.type)) {
      setError('Please select a PDF, JPG, JPEG, PNG or WEBP file.')
      setFile(null)
      return
    }

    if (selectedFile.size > 10 * 1024 * 1024) {
      setError('File size must be less than 10 MB.')
      setFile(null)
      return
    }

    setError('')
    setResult(null)
    setFile(selectedFile)
  }

  const handleChooseFile = () => {
    fileInputRef.current?.click()
  }

  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    setIsDragging(false)
    handleFileChange(event.dataTransfer.files?.[0])
  }

  const handleRemove = () => {
    setFile(null)
    setResult(null)
    setError('')

    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleAnalysis = async () => {
    if (!file) {
      setError('Please select a document first.')
      return
    }

    setLoading(true)
    setError('')
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await fetch(
        'http://127.0.0.1:8000/api/verify',
        {
          method: 'POST',
          body: formData,
        },
      )

      const rawResponse = await response.text()

      let data: any

      try {
        data = JSON.parse(rawResponse)
      } catch {
        throw new Error('Backend returned an invalid response.')
      }

      if (!response.ok) {
        throw new Error(
          data.detail || 'Document analysis failed.',
        )
      }

      setResult(data)
    } catch (error) {
      setError(
        error instanceof Error
          ? error.message
          : 'Unable to connect to VeriX backend.',
      )
    } finally {
      setLoading(false)
    }
  }

  const riskLevel =
    result?.risk_assessment.level?.toUpperCase() || ''

  const isUnknownDocument =
    result?.document_type.detected?.toUpperCase() === 'UNKNOWN'

  const riskClass =
    riskLevel === 'HIGH'
      ? 'text-red-300'
      : riskLevel === 'MEDIUM'
        ? 'text-amber-300'
        : isUnknownDocument
          ? 'text-slate-300'
          : 'text-emerald-300'

  const riskBorder =
    riskLevel === 'HIGH'
      ? 'border-red-400/30'
      : riskLevel === 'MEDIUM'
        ? 'border-amber-400/30'
        : isUnknownDocument
          ? 'border-slate-400/20'
          : 'border-emerald-400/30'

  const riskBg =
    riskLevel === 'HIGH'
      ? 'bg-red-400/10'
      : riskLevel === 'MEDIUM'
        ? 'bg-amber-400/10'
        : isUnknownDocument
          ? 'bg-slate-400/5'
          : 'bg-emerald-400/10'

  const riskProgress =
    Math.min(result?.risk_assessment.score ?? 0, 100)

  return (
    <div className="verix-app min-h-screen overflow-hidden bg-[#020617] text-white selection:bg-cyan-300/30">
      {/* Animated background */}
      <div className="pointer-events-none fixed inset-0 overflow-hidden">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_-10%,rgba(34,211,238,0.16),transparent_38%)]" />
        <div className="absolute inset-0 opacity-[0.045] [background-image:linear-gradient(rgba(255,255,255,.8)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.8)_1px,transparent_1px)] [background-size:44px_44px]" />
        <div className="absolute left-[-180px] top-[-180px] h-[460px] w-[460px] rounded-full bg-cyan-500/15 blur-[110px]" />
        <div className="absolute bottom-[-220px] right-[-180px] h-[500px] w-[500px] rounded-full bg-blue-600/15 blur-[120px]" />
        <div className="absolute left-1/2 top-1/3 h-32 w-32 -translate-x-1/2 rounded-full border border-cyan-400/10" />
      </div>

      <div className="relative mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">

        {/* NAVBAR */}
        <header className="mb-12 flex items-center justify-between border-b border-white/10 pb-5 animate-fade-down">
          <div className="flex items-center gap-3">
            <div className="relative flex h-11 w-11 items-center justify-center rounded-2xl bg-gradient-to-br from-cyan-300 to-blue-500 font-black text-slate-950 shadow-lg shadow-cyan-500/30 transition duration-500 hover:rotate-6 hover:scale-110">
              <span className="absolute inset-0 rounded-2xl bg-cyan-300/30 blur-md animate-pulse" />
              <span className="relative">V</span>
            </div>

            <div>
              <h1 className="text-lg font-bold tracking-tight">
                VeriX
              </h1>

              <p className="text-[10px] uppercase tracking-[0.25em] text-slate-500">
                Verification Intelligence
              </p>
            </div>
          </div>

          <div className="hidden items-center gap-2 rounded-full border border-emerald-400/20 bg-emerald-400/5 px-3 py-1.5 text-xs text-emerald-300 sm:flex">
            <span className="h-2 w-2 rounded-full bg-emerald-400" />
            System Operational
          </div>
        </header>

        {/* HERO */}
        <section className="relative mb-10 animate-fade-up">
          <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-cyan-300/20 bg-cyan-300/[0.08] px-4 py-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-200 shadow-[0_0_35px_rgba(34,211,238,0.08)]">
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full rounded-full bg-cyan-300 opacity-60" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-cyan-300 shadow-[0_0_16px_rgba(34,211,238,1)]" />
            </span>
            AI Document Verification
            <span className="ml-1 rounded-full bg-white/5 px-2 py-0.5 text-[9px] tracking-wider text-slate-400">LIVE</span>
          </div>

          <div className="relative">
            <div className="pointer-events-none absolute -left-8 -top-12 h-28 w-28 rounded-full border border-cyan-400/10" />
            <h2 className="max-w-4xl text-4xl font-black tracking-tight sm:text-5xl lg:text-7xl">
              Verify documents with
              <span className="block bg-gradient-to-r from-cyan-300 via-white to-blue-400 bg-clip-text text-transparent">
                evidence-driven analysis.
              </span>
            </h2>
          </div>

          <p className="mt-5 max-w-2xl text-base leading-7 text-slate-400 sm:text-lg">
            Upload an identity or official document. VeriX combines
            <span className="text-slate-200"> OCR</span>, validation,
            forensic indicators and explainable risk signals into one
            verification report.
          </p>
          <div className="mt-7 flex flex-wrap gap-2">
            {['OCR Engine', 'Rule Validation', 'Forensic Signals', 'Explainable Risk'].map((item) => (
              <span
                key={item}
                className="rounded-full border border-white/10 bg-white/[0.035] px-3 py-1.5 text-xs text-slate-400 backdrop-blur transition duration-300 hover:-translate-y-1 hover:border-cyan-400/30 hover:text-cyan-200"
              >
                {item}
              </span>
            ))}
          </div>
        </section>

        {/* UPLOAD WORKSPACE */}
        <section className="rounded-[28px] border border-white/10 bg-white/[0.045] p-4 shadow-2xl shadow-black/30 backdrop-blur-xl sm:p-6 lg:p-8 animate-fade-up">
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.webp"
            className="hidden"
            onChange={(event) =>
              handleFileChange(event.target.files?.[0])
            }
          />

          {!file ? (
            <div
              onClick={handleChooseFile}
              onDragOver={(event) => {
                event.preventDefault()
                setIsDragging(true)
              }}
              onDragLeave={() => setIsDragging(false)}
              onDrop={handleDrop}
              className={`group relative cursor-pointer overflow-hidden rounded-[24px] border border-dashed px-6 py-16 text-center transition-all duration-500 sm:px-10 ${
                isDragging
                  ? 'scale-[1.015] border-cyan-300 bg-cyan-400/[0.09] shadow-[0_0_60px_rgba(34,211,238,0.12)]'
                  : 'border-slate-700 bg-slate-950/75 hover:-translate-y-1 hover:border-cyan-400/50 hover:bg-cyan-400/[0.025] hover:shadow-[0_0_50px_rgba(34,211,238,0.06)]'
              }`}
            >
              <div className="pointer-events-none absolute inset-x-12 top-0 h-px bg-gradient-to-r from-transparent via-cyan-300 to-transparent opacity-50" />
              <div className="pointer-events-none absolute right-5 top-5 h-8 w-8 border-r border-t border-cyan-400/30" />
              <div className="pointer-events-none absolute bottom-5 left-5 h-8 w-8 border-b border-l border-cyan-400/30" />
              <div className="relative mx-auto flex h-24 w-24 items-center justify-center rounded-[30px] border border-cyan-400/25 bg-cyan-400/10 text-4xl text-cyan-300 shadow-[0_0_45px_rgba(34,211,238,0.12)] transition duration-500 group-hover:-translate-y-2 group-hover:scale-110">
                <span className="absolute inset-2 rounded-[24px] border border-cyan-300/10" />
                <span className="relative transition-transform duration-300 group-hover:-translate-y-1">↑</span>
              </div>

              <h3 className="mt-7 text-2xl font-bold">
                Upload document
              </h3>

              <p className="mx-auto mt-3 max-w-lg text-sm leading-6 text-slate-400">
                Drag and drop your document here or select a file
                from your device for verification.
              </p>

              <button
                type="button"
                onClick={(event) => {
                  event.stopPropagation()
                  handleChooseFile()
                }}
                className="mt-7 rounded-xl bg-cyan-400 px-7 py-3 font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:-translate-y-0.5 hover:bg-cyan-300"
              >
                Choose Document
              </button>

              <div className="mt-6 flex flex-wrap justify-center gap-2 text-xs text-slate-500">
                <span className="rounded-full border border-white/10 px-3 py-1">
                  PDF
                </span>

                <span className="rounded-full border border-white/10 px-3 py-1">
                  JPG
                </span>

                <span className="rounded-full border border-white/10 px-3 py-1">
                  PNG
                </span>

                <span className="rounded-full border border-white/10 px-3 py-1">
                  WEBP
                </span>

                <span className="rounded-full border border-white/10 px-3 py-1">
                  Max 10 MB
                </span>
              </div>
            </div>
          ) : (
            <div className="rounded-[24px] border border-cyan-400/20 bg-slate-950/70 p-5 sm:p-7">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl bg-cyan-400/10 text-2xl text-cyan-300">
                    {file.type === 'application/pdf' ? 'PDF' : 'IMG'}
                  </div>

                  <div className="min-w-0">
                    <p className="text-xs font-semibold uppercase tracking-widest text-cyan-400">
                      Document Ready
                    </p>

                    <h3 className="mt-1 truncate text-lg font-bold">
                      {file.name}
                    </h3>

                    <p className="mt-1 text-sm text-slate-500">
                      {(file.size / (1024 * 1024)).toFixed(2)} MB
                      {' • '}
                      {file.type === 'application/pdf'
                        ? 'PDF document'
                        : 'Image document'}
                    </p>
                  </div>
                </div>

                <div className="flex flex-wrap gap-3">
                  <button
                    type="button"
                    onClick={handleChooseFile}
                    disabled={loading}
                    className="rounded-xl border border-white/10 bg-white/5 px-5 py-3 text-sm font-semibold transition hover:bg-white/10 disabled:opacity-50"
                  >
                    Change
                  </button>

                  <button
                    type="button"
                    onClick={handleRemove}
                    disabled={loading}
                    className="rounded-xl border border-red-400/20 bg-red-400/5 px-5 py-3 text-sm font-semibold text-red-300 transition hover:bg-red-400/10 disabled:opacity-50"
                  >
                    Remove
                  </button>

                  <button
                    type="button"
                    onClick={handleAnalysis}
                    disabled={loading}
                    className="rounded-xl bg-cyan-400 px-6 py-3 text-sm font-bold text-slate-950 shadow-lg shadow-cyan-500/20 transition hover:-translate-y-0.5 hover:bg-cyan-300 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {loading ? 'Analyzing...' : 'Start Analysis'}
                  </button>
                </div>
              </div>

              {loading && (
                <div className="relative mt-6 overflow-hidden rounded-2xl border border-cyan-400/20 bg-cyan-400/[0.06] p-5 shadow-[0_0_45px_rgba(34,211,238,0.06)]">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="font-semibold text-cyan-300">
                        VeriX is analyzing your document
                      </p>

                      <p className="mt-1 text-sm text-slate-500">
                        OCR → Validation → Forensics → Risk Assessment
                      </p>
                    </div>

                    <div className="h-6 w-6 animate-spin rounded-full border-2 border-cyan-400/20 border-t-cyan-400" />
                  </div>

                  <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-800">
                    <div className="h-full w-2/3 rounded-full bg-gradient-to-r from-cyan-400 via-white to-cyan-400 animate-loading-bar" />
                  </div>
                  <div className="mt-4 grid grid-cols-4 gap-2 text-[10px] uppercase tracking-wider text-slate-500">
                    {['OCR', 'Validation', 'Forensics', 'Risk'].map((step, index) => (
                      <div key={step} className="flex items-center gap-1.5">
                        <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulse" />
                        {step}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {error && (
            <div className="mt-5 rounded-2xl border border-red-400/20 bg-red-400/5 p-4 text-sm text-red-300">
              <span className="font-bold">Error:</span> {error}
            </div>
          )}
        </section>

        {/* RESULT */}
        {result && (
          <section className="mt-12 space-y-6">
            {/* RESULT OVERVIEW */}
            <div className="rounded-[28px] border border-white/10 bg-white/[0.045] p-5 shadow-2xl shadow-black/20 backdrop-blur-xl animate-fade-up sm:p-7 lg:p-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">
                    <span className="h-2 w-2 rounded-full bg-cyan-400" />
                    Verification Complete
                  </div>

                  <h2 className="mt-3 text-3xl font-black sm:text-4xl">
                    {result.document_type.detected}
                  </h2>

                  <p className="mt-2 max-w-xl truncate text-sm text-slate-500">
                    {result.document.filename}
                  </p>
                </div>

                <div
                  className={`relative min-w-[240px] overflow-hidden rounded-3xl border ${riskBorder} ${riskBg} p-5`}
                >
                  <div className="absolute -right-10 -top-10 h-28 w-28 rounded-full bg-white/5 blur-2xl" />
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold uppercase tracking-widest text-slate-400">
                      {isUnknownDocument ? 'Verification Status' : 'Technical Risk'}
                    </span>
                    <span className={`rounded-full border border-white/10 bg-black/20 px-2.5 py-1 text-xs font-bold ${riskClass}`}>
                      {isUnknownDocument ? 'UNAVAILABLE' : riskLevel}
                    </span>
                  </div>

                  <div className="mt-4 flex items-center gap-5">
                    {isUnknownDocument ? (
                      <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full border border-slate-400/20 bg-slate-400/5">
                        <div className="absolute inset-1.5 rounded-full border border-slate-400/10" />
                        <span className="px-2 text-center text-[10px] font-bold uppercase leading-4 tracking-wider text-slate-300">
                          N/A
                        </span>
                      </div>
                    ) : (
                      <div
                        className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full animate-score-pop"
                        style={{
                          background: `conic-gradient(currentColor ${riskProgress}%, rgba(148,163,184,.12) ${riskProgress}% 100%)`,
                        }}
                      >
                        <div className="absolute inset-1.5 flex flex-col items-center justify-center rounded-full bg-[#07101f]">
                          <span className={`text-3xl font-black ${riskClass}`}>
                            {result.risk_assessment.score}
                          </span>
                          <span className="text-[9px] uppercase tracking-widest text-slate-500">/ 100</span>
                        </div>
                      </div>
                    )}

                    <div className="min-w-0">
                      <p className={`text-lg font-black ${riskClass}`}>
                        {isUnknownDocument
                          ? 'Insufficient Evidence'
                          : riskLevel === 'HIGH'
                            ? 'Attention Required'
                            : riskLevel === 'MEDIUM'
                              ? 'Review Signals'
                              : 'Low Technical Risk'}
                      </p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        {isUnknownDocument
                          ? 'Document type could not be confidently identified.'
                          : 'Based on available verification evidence.'}
                      </p>
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-7 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <Metric
                  label="File Type"
                  value={result.document.file_type}
                />

                <Metric
                  label="File Size"
                  value={`${(result.document.size_bytes / 1024).toFixed(1)} KB`}
                />

                <Metric
                  label="OCR Confidence"
                  value={`${result.ocr.confidence}%`}
                />

                <Metric
                  label="OCR Characters"
                  value={result.ocr.text_length.toLocaleString()}
                />
              </div>
            </div>

            {/* AADHAAR VALIDATION */}
            {result.document_type.detected === 'Aadhaar' &&
              result.validation && (
                <Section
                  title="Aadhaar Validation"
                  eyebrow="Document Rules"
                >
                  <div className="grid gap-4 md:grid-cols-3">
                    <StatusCard
                      label="Number Detected"
                      value={
                        result.validation.number_found
                          ? 'YES'
                          : 'NO'
                      }
                      positive={!!result.validation.number_found}
                    />

                    <StatusCard
                      label="Format Check"
                      value={
                        result.validation.format_valid
                          ? 'VALID'
                          : 'INVALID'
                      }
                      positive={!!result.validation.format_valid}
                    />

                    <StatusCard
                      label="Verhoeff Check"
                      value={
                        result.validation.verhoeff_valid
                          ? 'PASSED'
                          : result.validation.number_found
                            ? 'FAILED'
                            : 'NOT AVAILABLE'
                      }
                      positive={
                        !!result.validation.verhoeff_valid
                      }
                    />
                  </div>
                </Section>
              )}

            {/* FORENSICS */}
            <Section
              title="Forensic Analysis"
              eyebrow="Technical Signals"
            >
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <StatusCard
                  label="Image Quality"
                  value={
                    result.image_quality.issues.length === 0
                      ? 'GOOD'
                      : 'CHECK'
                  }
                  positive={
                    result.image_quality.issues.length === 0
                  }
                />

                <Metric
                  label="Blur Score"
                  value={`${result.image_quality.blur_score}`}
                />

                <StatusCard
                  label="ELA Analysis"
                  value={
                    result.forensics.ela?.suspicious
                      ? 'ANOMALY'
                      : 'NO STRONG SIGNAL'
                  }
                  positive={!result.forensics.ela?.suspicious}
                />

                <StatusCard
                  label="QR Analysis"
                  value={
                    result.forensics.qr?.decoded
                      ? 'DECODED'
                      : result.forensics.qr?.detected
                        ? 'DETECTED'
                        : 'NOT FOUND'
                  }
                  positive={!!result.forensics.qr?.decoded}
                />
              </div>

              {result.image_quality.issues.length > 0 && (
                <div className="mt-6">
                  <p className="mb-3 text-sm font-semibold text-slate-300">
                    Image Quality Signals
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {result.image_quality.issues.map(
                      (issue) => (
                        <span
                          key={issue}
                          className="rounded-full border border-amber-400/20 bg-amber-400/5 px-3 py-1.5 text-xs font-medium text-amber-300"
                        >
                          {issue.replaceAll('_', ' ')}
                        </span>
                      ),
                    )}
                  </div>
                </div>
              )}
            </Section>

            {/* CONSISTENCY */}
            <Section
              title="Consistency Check"
              eyebrow="Cross-Signal Analysis"
            >
              <div
                className={`rounded-2xl border p-5 ${
                  result.consistency.consistent
                    ? 'border-emerald-400/20 bg-emerald-400/5'
                    : 'border-red-400/20 bg-red-400/5'
                }`}
              >
                <div className="flex items-center gap-3">
                  <div
                    className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                      result.consistency.consistent
                        ? 'bg-emerald-400/10 text-emerald-300'
                        : 'bg-red-400/10 text-red-300'
                    }`}
                  >
                    {result.consistency.consistent ? '✓' : '!'}
                  </div>

                  <div>
                    <p
                      className={`font-bold ${
                        result.consistency.consistent
                          ? 'text-emerald-300'
                          : 'text-red-300'
                      }`}
                    >
                      {result.consistency.consistent
                        ? 'CONSISTENT'
                        : 'MISMATCH DETECTED'}
                    </p>

                    <p className="mt-1 text-xs text-slate-500">
                      Comparison of available verification signals
                    </p>
                  </div>
                </div>
              </div>

              {result.consistency.mismatches.length > 0 && (
                <div className="mt-4 space-y-2">
                  {result.consistency.mismatches.map(
                    (item) => (
                      <div
                        key={item}
                        className="rounded-xl border border-red-400/10 bg-red-400/5 p-4 text-sm text-slate-300"
                      >
                        {item}
                      </div>
                    ),
                  )}
                </div>
              )}
            </Section>

            {/* RISK */}
            <Section
              title="Risk Assessment"
              eyebrow="Explainable Analysis"
            >
              <div className="rounded-2xl border border-white/10 bg-slate-950/70 p-5">
                {isUnknownDocument && (
                  <div className="mb-4 rounded-xl border border-slate-400/15 bg-slate-400/5 p-4">
                    <p className="font-semibold text-slate-200">
                      Risk Score: Not Available
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      VeriX could not confidently identify the document type, so document-specific validation could not be performed.
                    </p>
                  </div>
                )}

                <p className="text-sm leading-6 text-slate-400">
                  {result.risk_assessment.technical_assessment ||
                    'Technical risk assessment generated from available verification signals.'}
                </p>

                {result.risk_assessment.disclaimer && (
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    {result.risk_assessment.disclaimer}
                  </p>
                )}
              </div>

              {result.risk_assessment.signals.length > 0 ? (
                <div className="mt-5 space-y-3">
                  {result.risk_assessment.signals.map(
                    (signal, index) => (
                      <div
                        key={`${signal.signal}-${index}`}
                        className="rounded-2xl border border-white/10 bg-slate-950/70 p-5 transition hover:border-cyan-400/20"
                      >
                        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                          <div>
                            <p className="font-semibold capitalize">
                              {signal.signal.replaceAll('_', ' ')}
                            </p>

                            {signal.reason && (
                              <p className="mt-2 text-xs leading-5 text-slate-500">
                                {signal.reason}
                              </p>
                            )}
                          </div>

                          <div className="flex items-center gap-2">
                            <span className="rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-300">
                              +{signal.points} points
                            </span>

                            <span className="rounded-full border border-white/10 px-3 py-1 text-xs text-slate-400">
                              {signal.severity}
                            </span>
                          </div>
                        </div>
                      </div>
                    ),
                  )}
                </div>
              ) : (
                <div className="mt-5 rounded-2xl border border-emerald-400/20 bg-emerald-400/5 p-5 text-sm text-emerald-300">
                  No significant technical risk signals detected.
                </div>
              )}
            </Section>

            {/* OCR */}
            <Section
              title="OCR Extraction"
              eyebrow={`${result.ocr.text_length.toLocaleString()} characters extracted`}
            >
              <div className="overflow-hidden rounded-2xl border border-white/10 bg-slate-950">
                <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
                  <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Extracted Text
                  </span>

                  <span className="text-xs text-cyan-400">
                    {result.ocr.confidence}% confidence
                  </span>
                </div>

                <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-5 text-sm leading-7 text-slate-400">
                  {result.ocr.text ||
                    'No OCR text extracted.'}
                </pre>
              </div>
            </Section>

            {/* TECHNICAL DISCLAIMER */}
            <div className="rounded-2xl border border-white/10 bg-white/[0.025] p-5 text-xs leading-6 text-slate-500">
              <span className="font-semibold text-slate-400">
                Technical note:
              </span>{' '}
              VeriX risk assessment is based on available OCR,
              validation, image-quality and forensic signals. These
              signals are technical indicators and do not independently
              prove legal authenticity or fraud.
            </div>
          </section>
        )}

        {/* PIPELINE */}
        <section className="mt-12">
          <div className="mb-5">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">
              Verification Pipeline
            </p>

            <h3 className="mt-2 text-2xl font-bold">
              How VeriX analyzes a document
            </h3>
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <PipelineCard
              number="01"
              title="Document Intelligence"
              description="Identify the document type and extract relevant information using OCR."
            />

            <PipelineCard
              number="02"
              title="Validation & Forensics"
              description="Apply document rules and analyze technical forensic indicators."
            />

            <PipelineCard
              number="03"
              title="Risk Assessment"
              description="Combine available evidence into an explainable technical risk assessment."
            />
          </div>
        </section>

        {/* FOOTER */}
        <footer className="mt-14 border-t border-white/10 py-6 text-center text-xs text-slate-600">
          VeriX • AI-Powered Document Verification Intelligence
        </footer>
      </div>
    </div>
  )
}

/* =========================
   REUSABLE UI COMPONENTS
========================= */

function Metric({
  label,
  value,
}: {
  label: string
  value: string
}) {
  return (
    <div className="group rounded-2xl border border-white/5 bg-slate-950/70 p-4 shadow-lg shadow-black/10 transition duration-300 hover:-translate-y-1 hover:border-cyan-400/20 hover:bg-slate-900/80 hover:shadow-cyan-500/5">
      <p className="text-xs uppercase tracking-wider text-slate-500">
        {label}
      </p>

      <p className="mt-2 truncate text-sm font-bold text-slate-200">
        {value}
      </p>
    </div>
  )
}

function StatusCard({
  label,
  value,
  positive,
}: {
  label: string
  value: string
  positive: boolean
}) {
  return (
    <div className="group rounded-2xl border border-white/5 bg-slate-950/70 p-5 shadow-lg shadow-black/10 transition duration-300 hover:-translate-y-1 hover:border-cyan-400/20 hover:bg-slate-900/80 hover:shadow-cyan-500/5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-xs uppercase tracking-wider text-slate-500">
          {label}
        </p>

        <span
          className={`h-2.5 w-2.5 rounded-full ${
            positive
              ? 'bg-emerald-400'
              : 'bg-amber-400'
          }`}
        />
      </div>

      <p
        className={`mt-4 text-lg font-black ${
          positive
            ? 'text-emerald-300'
            : 'text-amber-300'
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function Section({
  title,
  eyebrow,
  children,
}: {
  title: string
  eyebrow: string
  children: ReactNode
}) {
  return (
    <div className="rounded-[28px] border border-white/10 bg-white/[0.035] p-5 shadow-xl shadow-black/10 backdrop-blur-xl transition duration-500 hover:border-white/15 sm:p-7">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-cyan-400">
          {eyebrow}
        </p>

        <h3 className="mt-2 text-2xl font-bold">
          {title}
        </h3>
      </div>

      {children}
    </div>
  )
}

function PipelineCard({
  number,
  title,
  description,
}: {
  number: string
  title: string
  description: string
}) {
  return (
    <div className="group relative overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025] p-6 transition duration-500 hover:-translate-y-2 hover:border-cyan-400/30 hover:bg-cyan-400/[0.035] hover:shadow-[0_15px_45px_rgba(34,211,238,0.08)]">
      <div className="absolute right-0 top-0 h-24 w-24 translate-x-8 -translate-y-8 rounded-full bg-cyan-400/10 blur-2xl transition duration-500 group-hover:scale-150" />
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-cyan-400">
          {number}
        </span>

        <span className="h-px w-12 bg-white/10 transition group-hover:w-16 group-hover:bg-cyan-400/40" />
      </div>

      <h4 className="mt-6 text-lg font-bold">
        {title}
      </h4>

      <p className="mt-3 text-sm leading-6 text-slate-500">
        {description}
      </p>
    </div>
  )
}

export default Verification