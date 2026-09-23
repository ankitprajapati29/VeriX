import { useEffect, useRef, useState } from 'react'
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

type FaceDetectionResult = {
  available?: boolean
  detected?: boolean
  count?: number
  status?: string
  faces?: Array<{
    x: number
    y: number
    width: number
    height: number
  }>
  note?: string
}

type ForensicsResult = {
  face_detection?: FaceDetectionResult
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
  const [showPreview, setShowPreview] = useState(false)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [analysisStage, setAnalysisStage] = useState(0)

  useEffect(() => {
    if (!file) {
      setPreviewUrl(null)
      return
    }

    const url = URL.createObjectURL(file)
    setPreviewUrl(url)

    return () => URL.revokeObjectURL(url)
  }, [file])

  useEffect(() => {
    if (!loading) return

    setAnalysisStage(0)
    const timer = window.setInterval(() => {
      setAnalysisStage((current) => Math.min(current + 1, 3))
    }, 1200)

    return () => window.clearInterval(timer)
  }, [loading])

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({
      behavior: 'smooth',
      block: 'start',
    })
  }

  const handleNavigation = (item: string) => {
    const sectionMap: Record<string, string> = {
      Home: 'home',
      'Verify Document': 'verify',
      Results: 'results',
      'Supported Documents': 'supported',
      'How It Works': 'how-it-works',
      About: 'about',
    }

    if (item === 'Results' && !result) {
      setError('Analyze a document first to view the results.')
      scrollToSection('verify')
      return
    }

    scrollToSection(sectionMap[item])
  }

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
    setAnalysisStage(0)
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
    setShowPreview(false)
    setFile(null)
    setResult(null)
    setError('')
    setAnalysisStage(0)

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
    setAnalysisStage(0)

    try {
      const formData = new FormData()
      formData.append('file', file)

      const apiBaseUrl =
        window.location.hostname === 'localhost' ||
        window.location.hostname === '127.0.0.1'
          ? 'http://127.0.0.1:8000'
          : 'https://verix-backend-0y2g.onrender.com'

      const response = await fetch(
        `${apiBaseUrl}/api/verify`,
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
      setAnalysisStage(4)
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
    <>
      <style>{`
        @keyframes fadeUp {
          from { opacity: 0; transform: translateY(18px); }
          to { opacity: 1; transform: translateY(0); }
        }

        @keyframes modalIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }

        @keyframes modalCard {
          from { opacity: 0; transform: translateY(18px) scale(.98); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }

        @keyframes loadingBar {
          0% { transform: translateX(-100%); }
          50% { transform: translateX(0%); }
          100% { transform: translateX(150%); }
        }

        .animate-fade-up { animation: fadeUp .55s cubic-bezier(.22,1,.36,1) both; }
        .animate-modal-in { animation: modalIn .2s ease-out both; }
        .animate-modal-card { animation: modalCard .3s cubic-bezier(.22,1,.36,1) both; }
        .animate-loading-bar { animation: loadingBar 1.5s ease-in-out infinite; }
        .animate-score-pop { animation: fadeUp .65s cubic-bezier(.22,1,.36,1) both; }
      `}</style>
      <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] selection:bg-blue-100">
      <header className="sticky top-0 z-30 border-b border-slate-200 bg-white/95 backdrop-blur">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-4 sm:px-6 lg:px-8">
          <div className="flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-[#2563EB] text-lg font-black text-white shadow-sm">V</div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">VeriX</h1>
              <p className="text-[10px] font-medium uppercase tracking-[0.16em] text-slate-500">AI Document Verification</p>
            </div>
          </div>
          <nav className="hidden items-center gap-6 text-sm font-medium text-slate-600 lg:flex">
            {['Home', 'Verify Document', 'Results', 'Supported Documents', 'How It Works', 'About'].map((item) => (
              <button key={item} type="button" onClick={() => handleNavigation(item)} className={item === 'Verify Document'
                ? 'rounded-lg bg-blue-50 px-3 py-2 font-semibold text-[#2563EB]'
                : 'px-1 py-2 transition hover:text-[#2563EB]'}>
                {item}
              </button>
            ))}
          </nav>
          <div className="hidden items-center gap-2 text-xs font-medium text-emerald-700 sm:flex">
            <span className="h-2 w-2 rounded-full bg-emerald-500" /> System Operational
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-10">
        <section id="home" className="scroll-mt-24 grid items-center gap-8 pb-8 lg:grid-cols-[1.25fr_.75fr]">
          <div>
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-blue-100 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-[#2563EB]">
              <span className="h-2 w-2 rounded-full bg-[#2563EB]" /> AI-Powered • Secure • Accurate
            </div>
            <h2 className="max-w-3xl text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
              Verify a Document with <span className="text-[#2563EB]">AI</span>
            </h2>
            <p className="mt-5 max-w-2xl text-base leading-7 text-slate-600 sm:text-lg">
              Upload your document and get AI-powered analysis including OCR extraction, validation,
              forensic indicators, and technical risk assessment.
            </p>
          </div>
          <div className="hidden min-h-[230px] items-center justify-center lg:flex">
            <div className="relative flex h-56 w-72 items-center justify-center rounded-3xl border border-blue-100 bg-gradient-to-br from-blue-50 to-white shadow-sm">
              <div className="absolute right-7 top-6 h-16 w-24 rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="m-2 h-2 w-10 rounded bg-blue-100" /><div className="mx-2 h-2 w-14 rounded bg-slate-100" />
              </div>
              <div className="absolute bottom-7 left-8 flex h-20 w-24 items-center justify-center rounded-xl border border-slate-200 bg-white shadow-sm">
                <div className="h-10 w-8 rounded-full border-2 border-blue-200" />
              </div>
              <div className="z-10 flex h-20 w-20 items-center justify-center rounded-full bg-[#2563EB] text-3xl text-white shadow-lg shadow-blue-200">✓</div>
            </div>
          </div>
        </section>

        <section className="mb-6 rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="grid grid-cols-2 gap-4 md:grid-cols-5">
            {['Upload Document', 'OCR Extraction', 'Validation & Verification', 'Forensic Analysis', 'Results & Report'].map((step, index) => {
              const completed = result ? true : analysisStage > index
              const active = !result && (loading ? analysisStage === index : index === 0)

              return (
                <div key={step} className="flex items-center gap-3">
                  <div className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-sm font-bold transition-all duration-500 ${
                    completed
                      ? 'bg-emerald-500 text-white shadow-sm shadow-emerald-200'
                      : active
                        ? 'bg-[#2563EB] text-white shadow-md shadow-blue-200'
                        : 'bg-slate-100 text-slate-400'
                  }`}>
                    {completed ? '✓' : index + 1}
                  </div>
                  <span className={`text-xs font-semibold transition-colors ${
                    completed ? 'text-emerald-700' : active ? 'text-[#2563EB]' : 'text-slate-500'
                  }`}>
                    {step}
                  </span>
                </div>
              )
            })}
          </div>
        </section>

        <section id="verify" className="scroll-mt-24 grid gap-6 lg:grid-cols-[1fr_310px]">
          <div className="self-start rounded-2xl border border-slate-200 bg-white p-5 shadow-sm sm:p-7">
            <input ref={fileInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
              onChange={(event) => handleFileChange(event.target.files?.[0])} />

            {!file ? (
              <div onClick={handleChooseFile}
                onDragOver={(event) => { event.preventDefault(); setIsDragging(true) }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                className={`cursor-pointer rounded-2xl border-2 border-dashed p-10 text-center transition sm:p-14 ${
                  isDragging ? 'border-[#2563EB] bg-blue-50' : 'border-slate-200 bg-slate-50 hover:border-blue-300 hover:bg-blue-50/50'}`}>
                <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-blue-50 text-3xl text-[#2563EB]">↑</div>
                <h3 className="mt-5 text-2xl font-bold">Drag & drop your document here</h3>
                <p className="mt-2 text-sm text-slate-500">or click to browse files</p>
                <button type="button" onClick={(event) => { event.stopPropagation(); handleChooseFile() }}
                  className="mt-6 rounded-xl bg-[#2563EB] px-6 py-3 text-sm font-semibold text-white shadow-sm hover:bg-blue-700">
                  Choose File
                </button>
                <p className="mt-4 text-xs text-slate-400">Supports JPG, PNG, PDF, WEBP • Max 10MB</p>
              </div>
            ) : (
              <div className="rounded-2xl border border-blue-100 bg-blue-50/50 p-5">
                <div className="flex flex-col gap-5 sm:flex-row sm:items-center sm:justify-between">
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="relative flex h-14 w-14 shrink-0 items-center justify-center rounded-xl bg-white text-sm font-bold text-[#2563EB] shadow-sm ring-1 ring-blue-100">
                      {file.type === 'application/pdf' ? 'PDF' : 'IMG'}
                      <span className="absolute -right-1.5 -top-1.5 flex h-5 w-5 items-center justify-center rounded-full bg-emerald-500 text-[11px] font-black text-white shadow-sm">✓</span>
                    </div>
                    <div className="min-w-0">
                      <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-emerald-700">
                        <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
                        Ready for analysis
                      </span>
                      <h3 className="mt-2 truncate text-lg font-bold">{file.name}</h3>
                      <p className="mt-1 text-sm text-slate-500">{(file.size / (1024 * 1024)).toFixed(2)} MB • {file.type === 'application/pdf' ? 'PDF document' : 'Image document'}</p>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <button type="button" onClick={handleAnalysis} disabled={loading}
                      className="group relative order-first overflow-hidden rounded-xl bg-[#2563EB] px-5 py-3 text-sm font-bold text-white shadow-lg shadow-blue-200 transition duration-300 hover:-translate-y-0.5 hover:bg-blue-700 hover:shadow-xl hover:shadow-blue-300 disabled:cursor-not-allowed disabled:opacity-60 sm:order-none">
                      <span className="relative z-10 flex items-center gap-2">
                        {loading && <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />}
                        {loading ? 'Analyzing...' : 'Analyze Document'}
                        {!loading && <span className="transition-transform group-hover:translate-x-1">→</span>}
                      </span>
                      {!loading && <span className="absolute inset-0 -translate-x-full bg-white/15 transition-transform duration-500 group-hover:translate-x-full" />}
                    </button>
                    <button type="button" onClick={() => setShowPreview(true)} disabled={loading}
                      className="rounded-xl border border-blue-100 bg-white px-4 py-2.5 text-sm font-semibold text-[#2563EB] shadow-sm transition hover:-translate-y-0.5 hover:bg-blue-50 disabled:opacity-50">
                      View Document
                    </button>
                    <button type="button" onClick={handleChooseFile} disabled={loading}
                      className="rounded-xl border border-slate-200 bg-white px-4 py-2.5 text-sm font-semibold text-slate-700 transition hover:-translate-y-0.5 hover:bg-slate-50 disabled:opacity-50">
                      Change File
                    </button>
                    <button type="button" onClick={handleRemove} disabled={loading}
                      className="rounded-xl border border-red-100 bg-white px-4 py-2.5 text-sm font-semibold text-red-600 transition hover:-translate-y-0.5 hover:bg-red-50 disabled:opacity-50">
                      Remove
                    </button>
                  </div>
                </div>
                {loading && (
                  <div className="mt-5 rounded-2xl border border-blue-100 bg-gradient-to-br from-blue-50/80 to-white p-5 shadow-sm animate-fade-up">
                    <div className="flex items-center justify-between gap-4">
                      <div>
                        <p className="font-bold text-[#2563EB]">VeriX is analyzing your document</p>
                        <p className="mt-1 text-sm text-slate-500">Running OCR, validation, forensic checks and technical risk assessment.</p>
                      </div>
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-blue-100">
                        <div className="h-5 w-5 animate-spin rounded-full border-2 border-blue-200 border-t-[#2563EB]" />
                      </div>
                    </div>
                    <div className="mt-5 grid gap-2 sm:grid-cols-4">
                      {['OCR', 'Validation', 'Forensics', 'Risk'].map((step, index) => {
                        const completed = analysisStage > index
                        const active = analysisStage === index

                        return (
                          <div
                            key={step}
                            className={`rounded-xl border px-3 py-2.5 transition-all duration-300 ${
                              completed
                                ? 'border-emerald-200 bg-emerald-50'
                                : active
                                  ? 'border-blue-200 bg-blue-50 shadow-sm'
                                  : 'border-slate-200 bg-white'
                            }`}
                          >
                            <div className="flex items-center gap-2">
                              <span className={`flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-bold ${
                                completed
                                  ? 'bg-emerald-500 text-white'
                                  : active
                                    ? 'bg-[#2563EB] text-white'
                                    : 'bg-slate-100 text-slate-400'
                              }`}>
                                {completed ? '✓' : index + 1}
                              </span>
                              <span className={`text-xs font-semibold ${
                                completed ? 'text-emerald-700' : active ? 'text-[#2563EB]' : 'text-slate-500'
                              }`}>
                                {step}
                              </span>
                            </div>
                          </div>
                        )
                      })}
                    </div>
                    <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-slate-100">
                      <div
                        className="h-full rounded-full bg-[#2563EB] transition-all duration-700"
                        style={{ width: `${Math.min((analysisStage + 1) * 25, 100)}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            )}
            {error && <div className="mt-4 rounded-xl border border-red-100 bg-red-50 p-4 text-sm text-red-700"><span className="font-bold">Error:</span> {error}</div>}
          </div>

          <aside id="supported" className="scroll-mt-24 space-y-5">
            <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className="flex items-center justify-between"><h3 className="font-bold">Supported Documents</h3>
                <button type="button" className="text-xs font-semibold text-[#2563EB]">View All →</button></div>
              <div className="mt-4 grid grid-cols-2 gap-2">
                {['Aadhaar Card', 'PAN Card', 'Passport', 'Driving Licence', 'Visa', 'Other ID'].map((item) => (
                  <div key={item} className="rounded-xl border border-slate-100 bg-slate-50 p-3 text-xs font-medium text-slate-600">
                    <div className="mb-2 flex h-7 w-7 items-center justify-center rounded-lg bg-blue-50 text-[#2563EB]">□</div>{item}
                  </div>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-emerald-100 bg-emerald-50 p-5">
              <div className="flex items-center gap-3"><div className="flex h-9 w-9 items-center justify-center rounded-lg bg-white text-emerald-600 shadow-sm">🔒</div>
                <h3 className="font-bold text-emerald-900">Your Data is Safe</h3></div>
              <ul className="mt-4 space-y-2 text-xs leading-5 text-emerald-800">
                <li>✓ Documents are processed securely</li><li>✓ No data is stored permanently</li>
                <li>✓ Encrypted transmission (HTTPS)</li><li>✓ Used only for verification purposes</li>
              </ul>
            </div>
          </aside>
        </section>

        <section className="mt-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ['AI OCR Extraction', 'Extracts text from uploaded documents using OCR.', 'text-blue-600 bg-blue-50'],
            ['Document Validation', 'Checks document format and available validation signals.', 'text-emerald-600 bg-emerald-50'],
            ['Tampering Detection', 'Analyzes forensic signals for possible document manipulation.', 'text-red-600 bg-red-50'],
            ['Detailed Report', 'Provides risk assessment with detected signals and evidence.', 'text-purple-600 bg-purple-50'],
          ].map(([title, description, iconClass]) => (
            <div key={title} className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
              <div className={`mb-4 flex h-10 w-10 items-center justify-center rounded-xl ${iconClass}`}>✓</div>
              <h3 className="font-bold">{title}</h3><p className="mt-2 text-sm leading-6 text-slate-500">{description}</p>
            </div>
          ))}
        </section>
        {/* RESULT */}
        {result && (
          <section id="results" className="scroll-mt-24 mt-12 space-y-6">
            {/* RESULT OVERVIEW */}
            <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-2xl shadow-black/20 backdrop-blur-xl animate-fade-up sm:p-7 lg:p-8">
              <div className="flex flex-col gap-6 lg:flex-row lg:items-center lg:justify-between">
                <div>
                  <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.2em] text-[#2563EB]">
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
                    <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                      {isUnknownDocument ? 'Verification Status' : 'Technical Risk'}
                    </span>
                    <span className={`rounded-full border border-slate-200 bg-black/20 px-2.5 py-1 text-xs font-bold ${riskClass}`}>
                      {isUnknownDocument ? 'UNAVAILABLE' : riskLevel}
                    </span>
                  </div>

                  <div className="mt-4 flex items-center gap-5">
                    {isUnknownDocument ? (
                      <div className="relative flex h-24 w-24 shrink-0 items-center justify-center rounded-full border border-slate-400/20 bg-slate-400/5">
                        <div className="absolute inset-1.5 rounded-full border border-slate-400/10" />
                        <span className="px-2 text-center text-[10px] font-bold uppercase leading-4 tracking-wider text-slate-600">
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
                        <div className="absolute inset-1.5 flex flex-col items-center justify-center rounded-full bg-white">
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
                      {!isUnknownDocument && (
                        <div className="mt-3 inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-white/70 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-slate-600">
                          <span className={`h-1.5 w-1.5 rounded-full ${riskLevel === 'HIGH' ? 'bg-red-500' : riskLevel === 'MEDIUM' ? 'bg-amber-500' : 'bg-emerald-500'}`} />
                          {result.risk_assessment.signals.length} technical signal{result.risk_assessment.signals.length === 1 ? '' : 's'}
                        </div>
                      )}
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

              <div className="mt-4 rounded-2xl border border-blue-100 bg-blue-50/60 p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="text-xs font-bold uppercase tracking-[0.16em] text-blue-700">OCR Confidence</p>
                    <p className="mt-1 text-xs text-slate-500">Quality of text extracted from the uploaded document</p>
                  </div>
                  <span className="text-sm font-black text-[#2563EB]">{result.ocr.confidence}%</span>
                </div>
                <div className="mt-3 h-2 overflow-hidden rounded-full bg-white">
                  <div
                    className="h-full rounded-full bg-[#2563EB] transition-all duration-700"
                    style={{ width: `${Math.min(Math.max(result.ocr.confidence, 0), 100)}%` }}
                  />
                </div>
              </div>

              <div className="mt-5">
                <p className="mb-3 text-xs font-semibold uppercase tracking-[0.18em] text-slate-400">
                  Analysis Overview
                </p>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
                  <AnalysisMiniCard
                    label="OCR"
                    value={`${result.ocr.confidence}%`}
                    detail={result.ocr.text_length > 0 ? 'Text extracted' : 'No text extracted'}
                    tone={result.ocr.text_length > 0 ? 'blue' : 'amber'}
                  />
                  <AnalysisMiniCard
                    label="Document Type"
                    value={isUnknownDocument ? 'Unknown' : result.document_type.detected}
                    detail={isUnknownDocument ? 'Identification inconclusive' : 'Type identified'}
                    tone={isUnknownDocument ? 'slate' : 'green'}
                  />
                  <AnalysisMiniCard
                    label="Tampering"
                    value={result.forensics.ela?.suspicious ? 'Signal Found' : 'No Strong Signal'}
                    detail="ELA technical indicator"
                    tone={result.forensics.ela?.suspicious ? 'red' : 'green'}
                  />
                  <AnalysisMiniCard
                    label="QR"
                    value={
                      result.forensics.qr?.decoded
                        ? 'Decoded'
                        : result.forensics.qr?.detected
                          ? 'Detected'
                          : 'Not Found'
                    }
                    detail="QR analysis"
                    tone={result.forensics.qr?.decoded ? 'green' : 'slate'}
                  />
                  <AnalysisMiniCard
                    label="Face"
                    value={
                      result.forensics.face_detection?.detected
                        ? `${result.forensics.face_detection.count ?? 0} Detected`
                        : result.forensics.face_detection?.available === false
                          ? 'Unavailable'
                          : 'Not Detected'
                    }
                    detail={
                      result.forensics.face_detection?.available === false
                        ? 'Analysis unavailable'
                        : 'OpenCV face detection'
                    }
                    tone={
                      result.forensics.face_detection?.detected
                        ? 'green'
                        : 'slate'
                    }
                  />
                </div>
              </div>
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-blue-100 bg-blue-50/60 px-4 py-3">
                <div>
                  <p className="text-sm font-semibold text-slate-700">Need to inspect the source document?</p>
                  <p className="mt-1 text-xs text-slate-500">Open the uploaded file without leaving the analysis report.</p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowPreview(true)}
                  className="rounded-xl bg-white px-4 py-2 text-sm font-semibold text-[#2563EB] shadow-sm ring-1 ring-blue-100 transition hover:-translate-y-0.5 hover:bg-blue-50"
                >
                  View Document
                </button>
              </div>
            </div>

            {/* DOCUMENT EVIDENCE */}
            <Section
              title="Document Evidence"
              eyebrow="At-a-glance findings"
            >
              <div className="mb-5 flex flex-col gap-4 rounded-2xl border border-blue-100 bg-blue-50/50 p-4 sm:flex-row sm:items-center">
                <div className="flex h-28 w-28 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
                  {file?.type === 'application/pdf' ? (
                    <div className="text-center">
                      <div className="text-2xl">PDF</div>
                      <p className="mt-1 text-[9px] font-bold uppercase tracking-wider text-slate-400">Source</p>
                    </div>
                  ) : previewUrl ? (
                    <img
                      src={previewUrl}
                      alt="Uploaded document thumbnail"
                      className="h-full w-full object-contain"
                    />
                  ) : (
                    <span className="text-xs font-bold text-slate-400">Preview unavailable</span>
                  )}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-xs font-bold uppercase tracking-[0.16em] text-[#2563EB]">Source Document</p>
                  <p className="mt-1 truncate text-sm font-bold text-slate-800">{result.document.filename}</p>
                  <p className="mt-1 text-xs leading-5 text-slate-500">
                    Review the original uploaded evidence alongside VeriX analysis.
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setShowPreview(true)}
                  className="shrink-0 rounded-xl bg-white px-4 py-2.5 text-sm font-semibold text-[#2563EB] shadow-sm ring-1 ring-blue-100 transition hover:-translate-y-0.5 hover:bg-blue-50"
                >
                  View Document →
                </button>
              </div>

              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                <EvidenceItem
                  label="OCR"
                  value={`${result.ocr.confidence}% confidence`}
                  icon="Aa"
                />
                <EvidenceItem
                  label="Image Quality"
                  value={result.image_quality.issues.length === 0 ? 'Good' : 'Needs Review'}
                  icon="IQ"
                />
                <EvidenceItem
                  label="ELA"
                  value={result.forensics.ela?.suspicious ? 'Anomaly Signal' : 'No Strong Signal'}
                  icon="EL"
                />
                <EvidenceItem
                  label="Consistency"
                  value={
                    isUnknownDocument
                      ? 'Inconclusive'
                      : result.consistency.consistent
                        ? 'Consistent'
                        : 'Mismatch'
                  }
                  icon="CS"
                />
              </div>
            </Section>

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

                <StatusCard
                  label="Face Detection"
                  value={
                    result.forensics.face_detection?.detected
                      ? result.forensics.face_detection.count === 1
                        ? '1 FACE'
                        : `${result.forensics.face_detection.count} FACES`
                      : result.forensics.face_detection?.available === false
                        ? 'UNAVAILABLE'
                        : 'NOT FOUND'
                  }
                  positive={!!result.forensics.face_detection?.detected}
                />
              </div>

              <div className={`mt-5 rounded-2xl border p-4 ${
                result.forensics.ela?.suspicious
                  ? 'border-red-200 bg-red-50'
                  : 'border-emerald-200 bg-emerald-50'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                    result.forensics.ela?.suspicious
                      ? 'bg-red-100 text-red-700'
                      : 'bg-emerald-100 text-emerald-700'
                  }`}>
                    {result.forensics.ela?.suspicious ? '!' : '✓'}
                  </div>
                  <div>
                    <p className={`text-sm font-bold ${
                      result.forensics.ela?.suspicious ? 'text-red-800' : 'text-emerald-800'
                    }`}>
                      {result.forensics.ela?.suspicious ? 'Tampering signal requires review' : 'No strong tampering signal detected'}
                    </p>
                    <p className="mt-1 text-xs text-slate-500">
                      ELA is a technical forensic indicator and does not independently prove manipulation.
                    </p>
                  </div>
                </div>
              </div>

              <div className={`mt-5 rounded-2xl border p-4 ${
                result.forensics.face_detection?.detected
                  ? 'border-blue-200 bg-blue-50/70'
                  : 'border-slate-200 bg-slate-50'
              }`}>
                <div className="flex items-center gap-3">
                  <div className={`flex h-9 w-9 items-center justify-center rounded-xl ${
                    result.forensics.face_detection?.detected
                      ? 'bg-blue-100 text-[#2563EB]'
                      : 'bg-slate-200 text-slate-600'
                  }`}>
                    {result.forensics.face_detection?.detected ? '✓' : '—'}
                  </div>
                  <div className="min-w-0">
                    <p className={`text-sm font-bold ${
                      result.forensics.face_detection?.detected
                        ? 'text-blue-800'
                        : 'text-slate-700'
                    }`}>
                      {result.forensics.face_detection?.detected
                        ? `${result.forensics.face_detection.count ?? 0} face${(result.forensics.face_detection.count ?? 0) === 1 ? '' : 's'} detected`
                        : 'No face detected'}
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      OpenCV-based face detection is a technical image-analysis signal. It does not prove identity or document authenticity.
                    </p>
                  </div>
                </div>
              </div>

              {result.image_quality.issues.length > 0 && (
                <div className="mt-6">
                  <p className="mb-3 text-sm font-semibold text-slate-600">
                    Image Quality Signals
                  </p>

                  <div className="flex flex-wrap gap-2">
                    {result.image_quality.issues.map(
                      (issue) => (
                        <span
                          key={issue}
                          className="rounded-full border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-700"
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
              {isUnknownDocument ? (
                <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                  <div className="flex items-center gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-slate-200 text-slate-600">
                      —
                    </div>
                    <div>
                      <p className="font-bold text-slate-700">INCONCLUSIVE</p>
                      <p className="mt-1 text-xs leading-5 text-slate-500">
                        Document-specific consistency checks were not performed because the document type could not be confidently identified.
                      </p>
                    </div>
                  </div>
                </div>
              ) : (
                <>
                  <div
                    className={`rounded-2xl border p-5 ${
                      result.consistency.consistent
                        ? 'border-emerald-200 bg-emerald-50'
                        : 'border-red-200 bg-red-50'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div
                        className={`flex h-10 w-10 items-center justify-center rounded-xl ${
                          result.consistency.consistent
                            ? 'bg-emerald-400/10 text-emerald-700'
                            : 'bg-red-400/10 text-red-700'
                        }`}
                      >
                        {result.consistency.consistent ? '✓' : '!'}
                      </div>

                      <div>
                        <p
                          className={`font-bold ${
                            result.consistency.consistent
                              ? 'text-emerald-700'
                              : 'text-red-700'
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
                            className="rounded-xl border border-red-400/10 bg-red-50 p-4 text-sm text-slate-600"
                          >
                            {item}
                          </div>
                        ),
                      )}
                    </div>
                  )}
                </>
              )}
            </Section>

            {/* RISK */}
            <Section
              title="Risk Assessment"
              eyebrow="Explainable Analysis"
            >
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-5">
                {isUnknownDocument && (
                  <div className="mb-4 rounded-xl border border-slate-400/15 bg-slate-400/5 p-4">
                    <p className="font-semibold text-slate-800">
                      Risk Score: Not Available
                    </p>
                    <p className="mt-1 text-xs leading-5 text-slate-500">
                      VeriX could not confidently identify the document type, so document-specific validation could not be performed.
                    </p>
                  </div>
                )}

                <p className="text-sm leading-6 text-slate-500">
                  {result.risk_assessment.technical_assessment ||
                    'Technical risk assessment generated from available verification signals.'}
                </p>

                {result.risk_assessment.disclaimer && (
                  <p className="mt-2 text-xs leading-5 text-slate-500">
                    {result.risk_assessment.disclaimer}
                  </p>
                )}
              </div>

              {!isUnknownDocument && result.risk_assessment.signals.length > 0 ? (
                <div className="mt-5 space-y-3">
                  {result.risk_assessment.signals.map(
                    (signal, index) => (
                      <div
                        key={`${signal.signal}-${index}`}
                        className={`rounded-2xl border p-5 transition duration-300 hover:-translate-y-0.5 ${
                          signal.severity?.toUpperCase() === 'HIGH'
                            ? 'border-red-200 bg-red-50/50 hover:border-red-300'
                            : signal.severity?.toUpperCase() === 'MEDIUM'
                              ? 'border-amber-200 bg-amber-50/40 hover:border-amber-300'
                              : 'border-slate-200 bg-slate-50 hover:border-blue-200'
                        }`}
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
                            <span className="rounded-full border border-slate-200 bg-white/5 px-3 py-1 text-xs font-semibold text-slate-600">
                              +{signal.points} points
                            </span>

                            <span className="rounded-full border border-slate-200 px-3 py-1 text-xs text-slate-500">
                              {signal.severity}
                            </span>
                          </div>
                        </div>
                      </div>
                    ),
                  )}
                </div>
              ) : (
                <div className={`mt-5 rounded-2xl border p-5 text-sm ${
                  isUnknownDocument
                    ? 'border-slate-200 bg-slate-50 text-slate-600'
                    : 'border-emerald-200 bg-emerald-50 text-emerald-700'
                }`}>
                  {isUnknownDocument
                    ? 'No document-specific risk score is shown because the document type could not be confidently identified.'
                    : 'No significant technical risk signals detected.'}
                </div>
              )}
            </Section>

            {/* OCR */}
            <Section
              title="OCR Extraction"
              eyebrow={`${result.ocr.text_length.toLocaleString()} characters extracted`}
            >
              <div className="overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
                <div className="flex items-center justify-between border-b border-slate-200 px-5 py-3">
                  <span className="text-xs font-semibold uppercase tracking-widest text-slate-500">
                    Extracted Text
                  </span>

                  <span className="text-xs text-[#2563EB]">
                    {result.ocr.confidence}% confidence
                  </span>
                </div>

                <div className="px-5 pt-4">
                  <div className="h-1.5 overflow-hidden rounded-full bg-white">
                    <div
                      className="h-full rounded-full bg-[#2563EB]"
                      style={{ width: `${Math.min(Math.max(result.ocr.confidence, 0), 100)}%` }}
                    />
                  </div>
                </div>
                <pre className="max-h-80 overflow-auto whitespace-pre-wrap p-5 text-sm leading-7 text-slate-500">
                  {result.ocr.text ||
                    'No OCR text extracted.'}
                </pre>
              </div>
            </Section>

            {/* TECHNICAL DISCLAIMER */}
            <div className="rounded-2xl border border-slate-200 bg-white p-5 text-xs leading-6 text-slate-500">
              <span className="font-semibold text-slate-500">
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
        <section id="how-it-works" className="scroll-mt-24 mt-12">
          <div className="mb-5">
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#2563EB]">
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
        <footer id="about" className="scroll-mt-24 mt-14 border-t border-slate-200 py-6 text-center text-xs text-slate-600">
          VeriX • AI-Powered Document Verification Intelligence
        </footer>
      </main>

      {showPreview && file && previewUrl && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-slate-950/70 p-4 backdrop-blur-md animate-modal-in"
          role="dialog"
          aria-modal="true"
          aria-label="Document preview"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setShowPreview(false)
          }}
        >
          <div className="flex max-h-[92vh] w-full max-w-5xl flex-col overflow-hidden rounded-3xl border border-white/15 bg-white shadow-2xl animate-modal-card">
            <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.16em] text-[#2563EB]">Document Preview</p>
                <p className="mt-1 truncate text-sm font-bold text-slate-800">{file.name}</p>
              </div>
              <button
                type="button"
                onClick={() => setShowPreview(false)}
                className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-slate-100 text-lg font-semibold text-slate-600 transition hover:bg-slate-200 hover:text-slate-900"
                aria-label="Close document preview"
              >
                ×
              </button>
            </div>

            <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-slate-100 p-4 sm:p-8">
              {file.type === 'application/pdf' ? (
                <iframe
                  src={previewUrl}
                  title="Uploaded document PDF preview"
                  className="h-[70vh] w-full rounded-xl border border-slate-200 bg-white shadow-sm"
                />
              ) : (
                <img
                  src={previewUrl}
                  alt={`Preview of ${file.name}`}
                  className="max-h-[70vh] max-w-full rounded-xl border border-slate-200 bg-white object-contain shadow-lg"
                />
              )}
            </div>

            <div className="flex items-center justify-between gap-3 border-t border-slate-200 bg-white px-5 py-3">
              <p className="text-xs text-slate-500">
                {file.type === 'application/pdf' ? 'PDF document' : 'Image document'} • {(file.size / (1024 * 1024)).toFixed(2)} MB
              </p>
              <button
                type="button"
                onClick={() => setShowPreview(false)}
                className="rounded-xl bg-[#2563EB] px-4 py-2 text-sm font-semibold text-white transition hover:bg-blue-700"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
      </div>
    </>
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
    <div className="group rounded-2xl border border-slate-100 bg-slate-50 p-4 shadow-sm transition duration-300 hover:-translate-y-1 hover:border-blue-200 hover:bg-white hover:shadow-md">
      <p className="text-xs uppercase tracking-wider text-slate-500">
        {label}
      </p>

      <p className="mt-2 truncate text-sm font-bold text-slate-800">
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
    <div className="group rounded-2xl border border-slate-100 bg-slate-50 p-5 shadow-sm transition duration-300 hover:-translate-y-1 hover:border-blue-200 hover:bg-white hover:shadow-md">
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
            ? 'text-emerald-600'
            : 'text-amber-600'
        }`}
      >
        {value}
      </p>
    </div>
  )
}

function AnalysisMiniCard({
  label,
  value,
  detail,
  tone,
}: {
  label: string
  value: string
  detail: string
  tone: 'blue' | 'green' | 'red' | 'amber' | 'slate'
}) {
  const toneClasses = {
    blue: 'border-blue-100 bg-blue-50/70 text-blue-700',
    green: 'border-emerald-100 bg-emerald-50/70 text-emerald-700',
    red: 'border-red-100 bg-red-50/70 text-red-700',
    amber: 'border-amber-100 bg-amber-50/70 text-amber-700',
    slate: 'border-slate-200 bg-slate-50 text-slate-700',
  }

  return (
    <div className={`group rounded-2xl border p-4 transition duration-300 hover:-translate-y-1 hover:shadow-md ${toneClasses[tone]}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[11px] font-bold uppercase tracking-[0.14em] opacity-70">{label}</p>
        <span className="h-2 w-2 rounded-full bg-current opacity-70" />
      </div>
      <p className="mt-3 truncate text-sm font-black">{value}</p>
      <p className="mt-1 text-xs leading-5 opacity-70">{detail}</p>
    </div>
  )
}

function EvidenceItem({
  label,
  value,
  icon,
}: {
  label: string
  value: string
  icon: string
}) {
  return (
    <div className="group rounded-2xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-4 transition duration-300 hover:-translate-y-1 hover:border-blue-200 hover:shadow-md">
      <div className="flex items-center gap-3">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-50 text-[10px] font-black text-[#2563EB]">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-400">{label}</p>
          <p className="mt-1 truncate text-sm font-bold text-slate-800">{value}</p>
        </div>
      </div>
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
    <div className="rounded-[28px] border border-slate-200 bg-white p-5 shadow-xl shadow-black/10 backdrop-blur-xl transition duration-500 hover:border-white/15 sm:p-7">
      <div className="mb-6">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-[#2563EB]">
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
    <div className="group relative overflow-hidden rounded-2xl border border-slate-200 bg-white p-6 transition duration-500 hover:-translate-y-2 hover:border-cyan-400/30 hover:bg-cyan-400/[0.035] hover:shadow-[0_15px_45px_rgba(34,211,238,0.08)]">
      <div className="absolute right-0 top-0 h-24 w-24 translate-x-8 -translate-y-8 rounded-full bg-cyan-400/10 blur-2xl transition duration-500 group-hover:scale-150" />
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold tracking-widest text-[#2563EB]">
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