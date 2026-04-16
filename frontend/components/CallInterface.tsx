"use client";

import React, {
  useState,
  useEffect,
  useRef,
  useCallback,
} from "react";
import {
  Mic,
  MicOff,
  Phone,
  PhoneOff,
  ChevronDown,
  Code2,
  Activity,
  Clock,
  AlertCircle,
  RefreshCw,
  Loader2,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

type CallStatus = "idle" | "connecting" | "active" | "ending";

interface TranscriptEntry {
  id: number;
  role: "user" | "assistant";
  text: string;
}

interface HealthData {
  indexed_repos: string[];
  active_repo: string;
  status: string;
}

// ─── Waveform Bars ────────────────────────────────────────────────────────────

function WaveformBars({ active }: { active: boolean }) {
  const animations = [
    "animate-wave-1",
    "animate-wave-2",
    "animate-wave-3",
    "animate-wave-4",
    "animate-wave-3",
    "animate-wave-2",
    "animate-wave-1",
  ];
  return (
    <div className="flex items-center gap-[3px] h-10">
      {animations.map((anim, i) => (
        <div
          key={i}
          className={`w-1.5 rounded-full origin-bottom transition-all duration-150 ${
            active
              ? `bg-emerald-400 ${anim}`
              : "bg-emerald-900 h-1.5"
          }`}
          style={active ? { height: "100%" } : {}}
        />
      ))}
    </div>
  );
}

// ─── AI Avatar ────────────────────────────────────────────────────────────────

function AIAvatar({
  callStatus,
  isAiSpeaking,
  volumeLevel,
}: {
  callStatus: CallStatus;
  isAiSpeaking: boolean;
  volumeLevel: number;
}) {
  const isActive = callStatus === "active";
  const isConnecting = callStatus === "connecting";

  // Scale the outer ring based on volume
  const ringScale = isAiSpeaking ? 1 + volumeLevel * 0.3 : 1;

  return (
    <div className="relative flex items-center justify-center w-56 h-56 select-none">
      {/* Outermost pulse rings (when active) */}
      {isActive && (
        <>
          <div className="absolute inset-0 rounded-full border border-emerald-500/20 animate-pulse-ring" />
          <div className="absolute inset-0 rounded-full border border-emerald-500/10 animate-pulse-ring-slow" />
        </>
      )}

      {/* Volume ring */}
      {isAiSpeaking && (
        <div
          className="absolute inset-0 rounded-full border-2 border-emerald-400/60 transition-transform duration-75"
          style={{ transform: `scale(${ringScale})` }}
        />
      )}

      {/* Main avatar circle */}
      <div
        className={`relative w-44 h-44 rounded-full flex flex-col items-center justify-center overflow-hidden transition-all duration-500 scan-lines ${
          isActive
            ? "border-2 border-emerald-500/70 glow-green"
            : isConnecting
            ? "border-2 border-emerald-500/40 animate-pulse"
            : "border border-[#1f1f1f]"
        }`}
        style={{
          background: isActive
            ? "radial-gradient(circle at 40% 35%, #0f2d1f 0%, #050505 70%)"
            : "radial-gradient(circle at 40% 35%, #111111 0%, #050505 70%)",
        }}
      >
        {/* Connecting spinner */}
        {isConnecting && (
          <div className="absolute inset-0 flex items-center justify-center">
            <Loader2
              className="w-10 h-10 text-emerald-400 animate-spin"
              strokeWidth={1.5}
            />
          </div>
        )}

        {/* Idle / active content */}
        {!isConnecting && (
          <>
            {/* Logo icon */}
            <div className="mb-2">
              <Code2
                className={`w-10 h-10 transition-colors duration-300 ${
                  isActive ? "text-emerald-400" : "text-gray-600"
                }`}
                strokeWidth={1.5}
              />
            </div>

            {/* Waveform shown when active */}
            {isActive ? (
              <WaveformBars active={isAiSpeaking} />
            ) : (
              <p className="text-xs text-gray-600 mt-1 tracking-widest uppercase">
                SonarCode
              </p>
            )}
          </>
        )}

        {/* Subtle scanline overlay handled by CSS */}
      </div>

      {/* Status dot */}
      <div
        className={`absolute bottom-3 right-3 w-3.5 h-3.5 rounded-full border-2 border-[#050505] transition-colors duration-300 ${
          isActive
            ? "bg-emerald-400"
            : isConnecting
            ? "bg-yellow-400 animate-pulse"
            : "bg-gray-600"
        }`}
      />
    </div>
  );
}

// ─── Transcript Panel ─────────────────────────────────────────────────────────

function TranscriptPanel({ entries }: { entries: TranscriptEntry[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-[#1f1f1f]">
        <Activity className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
        <span className="text-xs text-gray-400 uppercase tracking-widest font-medium">
          Transcript
        </span>
        {entries.length > 0 && (
          <span className="ml-auto text-xs text-gray-600">
            {entries.length} msg{entries.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-center">
            <div className="w-10 h-10 rounded-full bg-[#1a1a1a] flex items-center justify-center">
              <Mic className="w-4 h-4 text-gray-600" strokeWidth={1.5} />
            </div>
            <p className="text-xs text-gray-600 leading-relaxed max-w-[180px]">
              Start a call and your conversation will appear here in real time.
            </p>
          </div>
        ) : (
          entries.map((entry) => (
            <div
              key={entry.id}
              className={`flex animate-slide-up ${
                entry.role === "user" ? "justify-end" : "justify-start"
              }`}
            >
              <div
                className={`max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed ${
                  entry.role === "user"
                    ? "bg-emerald-900/40 text-emerald-100 rounded-tr-sm"
                    : "bg-[#1a1a1a] text-gray-200 rounded-tl-sm"
                }`}
              >
                {entry.role === "assistant" && (
                  <p className="text-[10px] text-emerald-400/70 font-medium mb-1 uppercase tracking-widest">
                    SonarCode
                  </p>
                )}
                <p>{entry.text}</p>
              </div>
            </div>
          ))
        )}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}

// ─── Repo Selector ────────────────────────────────────────────────────────────

function RepoSelector({
  repos,
  selected,
  onChange,
  disabled,
}: {
  repos: string[];
  selected: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  if (repos.length === 0) return null;

  return (
    <div className="relative">
      <select
        value={selected}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        className={`appearance-none bg-[#0f0f0f] border border-[#1f1f1f] text-gray-300 text-xs rounded-lg pl-3 pr-8 py-2 focus:outline-none focus:border-emerald-500/50 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed max-w-[220px] truncate`}
      >
        {repos.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-gray-500 pointer-events-none" />
    </div>
  );
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function CallInterface() {
  const [repos, setRepos] = useState<string[]>([]);
  const [selectedRepo, setSelectedRepo] = useState("");
  const [callStatus, setCallStatus] = useState<CallStatus>("idle");
  const [isMuted, setIsMuted] = useState(false);
  const [isAiSpeaking, setIsAiSpeaking] = useState(false);
  const [volumeLevel, setVolumeLevel] = useState(0);
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [elapsedTime, setElapsedTime] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backendOk, setBackendOk] = useState<boolean | null>(null);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const vapiRef = useRef<any>(null);
  const entryIdRef = useRef(0);

  const BACKEND_URL =
    process.env.NEXT_PUBLIC_BACKEND_URL || "http://localhost:8000";
  const VAPI_KEY = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY || "";

  // ── Init Vapi SDK (browser only) ────────────────────────────────────────────
  useEffect(() => {
    if (!VAPI_KEY) {
      setError("NEXT_PUBLIC_VAPI_PUBLIC_KEY is not set. Check your .env.local file.");
      return;
    }

    let instance: any;

    import("@vapi-ai/web")
      .then(({ default: Vapi }) => {
        instance = new Vapi(VAPI_KEY);
        vapiRef.current = instance;

        instance.on("call-start", () => {
          setCallStatus("active");
          setIsMuted(false);
        });
        instance.on("call-end", () => {
          setCallStatus("idle");
          setIsAiSpeaking(false);
          setVolumeLevel(0);
        });
        instance.on("speech-start", () => setIsAiSpeaking(true));
        instance.on("speech-end", () => setIsAiSpeaking(false));
        instance.on("volume-level", (level: number) => setVolumeLevel(level));
        instance.on("message", (msg: any) => {
          if (msg.type === "transcript" && msg.transcriptType === "final") {
            setTranscript((prev) => [
              ...prev,
              {
                id: ++entryIdRef.current,
                role: msg.role as "user" | "assistant",
                text: msg.transcript,
              },
            ]);
          }
        });
        instance.on("error", (e: any) => {
          const msg = e?.error?.message || e?.message || "Unknown call error";
          setError(msg);
          setCallStatus("idle");
        });
      })
      .catch((e) => setError(`Failed to load Vapi SDK: ${e.message}`));

    return () => {
      instance?.stop();
    };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── Fetch repos on mount ────────────────────────────────────────────────────
  const fetchHealth = useCallback(() => {
    setBackendOk(null);
    fetch(`${BACKEND_URL}/health`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((data: HealthData) => {
        const r = data.indexed_repos || [];
        setRepos(r);
        if (r.length > 0 && !selectedRepo) setSelectedRepo(r[0]);
        setBackendOk(true);
        setError(null);
      })
      .catch((e) => {
        setBackendOk(false);
        setError(`Cannot reach backend: ${e.message}. Is it running?`);
      });
  }, [BACKEND_URL, selectedRepo]);

  useEffect(() => {
    fetchHealth();
  }, [fetchHealth]);

  // ── Elapsed time counter ────────────────────────────────────────────────────
  useEffect(() => {
    if (callStatus !== "active") {
      setElapsedTime(0);
      return;
    }
    const timer = setInterval(() => setElapsedTime((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [callStatus]);

  // ── Handlers ────────────────────────────────────────────────────────────────
  const handleStartCall = async () => {
    if (!vapiRef.current || !selectedRepo) return;
    setIsLoading(true);
    setError(null);
    setTranscript([]);

    try {
      // Tell the backend which repo is active
      const repoRes = await fetch(`${BACKEND_URL}/set-repo`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo: selectedRepo }),
      });
      if (!repoRes.ok) throw new Error(`set-repo failed: HTTP ${repoRes.status}`);

      // Get the full Vapi inline assistant config from the backend
      const cfgRes = await fetch(`${BACKEND_URL}/vapi-config`);
      if (!cfgRes.ok) throw new Error(`vapi-config failed: HTTP ${cfgRes.status}`);
      const config = await cfgRes.json();

      setCallStatus("connecting");
      await vapiRef.current.start(config);
    } catch (e: any) {
      setError(e?.message || "Failed to start call");
      setCallStatus("idle");
    } finally {
      setIsLoading(false);
    }
  };

  const handleEndCall = () => {
    if (!vapiRef.current) return;
    setCallStatus("ending");
    vapiRef.current.stop();
  };

  const handleToggleMute = () => {
    if (!vapiRef.current || callStatus !== "active") return;
    const next = !isMuted;
    vapiRef.current.setMuted(next);
    setIsMuted(next);
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60)
      .toString()
      .padStart(2, "0");
    const sec = (s % 60).toString().padStart(2, "0");
    return `${m}:${sec}`;
  };

  const isCallActive = callStatus === "active";
  const isCallBusy = callStatus === "connecting" || callStatus === "ending";
  const canCall = backendOk && repos.length > 0 && !!VAPI_KEY && !isLoading;

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col h-screen bg-[#050505] overflow-hidden">
      {/* ── Top bar ──────────────────────────────────────────────────────── */}
      <header className="flex items-center justify-between px-5 py-3 border-b border-[#1f1f1f] bg-[#050505]/80 backdrop-blur-sm z-10 flex-shrink-0">
        {/* Logo */}
        <div className="flex items-center gap-2.5">
          <div className="w-7 h-7 rounded-md bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center">
            <Code2 className="w-3.5 h-3.5 text-emerald-400" strokeWidth={2} />
          </div>
          <span className="text-sm font-semibold text-gray-100 tracking-tight">
            SonarCode
          </span>
          <span className="hidden sm:inline text-[10px] text-gray-600 uppercase tracking-widest border border-[#1f1f1f] rounded px-1.5 py-0.5">
            Voice Oracle
          </span>
        </div>

        {/* Repo selector + status */}
        <div className="flex items-center gap-3">
          {/* Backend status indicator */}
          <div className="hidden sm:flex items-center gap-1.5">
            <div
              className={`w-1.5 h-1.5 rounded-full ${
                backendOk === null
                  ? "bg-yellow-400 animate-pulse"
                  : backendOk
                  ? "bg-emerald-400"
                  : "bg-red-500"
              }`}
            />
            <span className="text-[10px] text-gray-600">
              {backendOk === null ? "connecting" : backendOk ? "backend ok" : "offline"}
            </span>
          </div>

          <RepoSelector
            repos={repos}
            selected={selectedRepo}
            onChange={setSelectedRepo}
            disabled={isCallActive || isCallBusy}
          />

          {/* Retry / refresh */}
          {backendOk === false && (
            <button
              onClick={fetchHealth}
              className="w-7 h-7 flex items-center justify-center rounded-lg border border-[#1f1f1f] text-gray-500 hover:text-gray-300 hover:border-gray-600 transition-colors"
              title="Retry backend connection"
            >
              <RefreshCw className="w-3 h-3" />
            </button>
          )}
        </div>
      </header>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <main className="flex flex-1 overflow-hidden">
        {/* Left: video call area */}
        <div className="flex-1 flex flex-col items-center justify-center gap-6 p-8 grid-bg relative">
          {/* Call timer */}
          {isCallActive && (
            <div className="absolute top-5 left-1/2 -translate-x-1/2 flex items-center gap-1.5 bg-[#0f0f0f]/80 border border-[#1f1f1f] rounded-full px-3 py-1 animate-fade-in">
              <Clock className="w-3 h-3 text-emerald-400" strokeWidth={2} />
              <span className="text-xs text-emerald-400 font-mono tabular-nums">
                {formatTime(elapsedTime)}
              </span>
            </div>
          )}

          {/* Avatar */}
          <AIAvatar
            callStatus={callStatus}
            isAiSpeaking={isAiSpeaking}
            volumeLevel={volumeLevel}
          />

          {/* Status label */}
          <div className="text-center space-y-1">
            <p className="text-sm font-medium text-gray-300">
              {callStatus === "idle" && "Ready to connect"}
              {callStatus === "connecting" && "Connecting…"}
              {callStatus === "active" &&
                (isAiSpeaking ? "SonarCode is speaking…" : "Listening…")}
              {callStatus === "ending" && "Ending call…"}
            </p>
            {selectedRepo && (
              <p className="text-xs text-gray-600">
                {callStatus === "idle" ? "will use " : "using "}
                <span className="text-emerald-500/70">{selectedRepo}</span>
              </p>
            )}
          </div>

          {/* No repos warning */}
          {backendOk && repos.length === 0 && (
            <div className="flex items-center gap-2 bg-yellow-900/20 border border-yellow-500/20 text-yellow-400/80 text-xs rounded-lg px-4 py-2.5 max-w-sm text-center">
              <AlertCircle className="w-4 h-4 flex-shrink-0" strokeWidth={1.5} />
              <span>
                No repos indexed yet. POST to{" "}
                <code className="text-yellow-300">/ingest</code> first.
              </span>
            </div>
          )}

          {/* Error banner */}
          {error && (
            <div className="flex items-start gap-2 bg-red-900/20 border border-red-500/20 text-red-400/80 text-xs rounded-lg px-4 py-2.5 max-w-sm animate-fade-in">
              <AlertCircle className="w-4 h-4 flex-shrink-0 mt-0.5" strokeWidth={1.5} />
              <span>{error}</span>
            </div>
          )}

          {/* Tip cards (idle only) */}
          {callStatus === "idle" && repos.length > 0 && (
            <div className="hidden md:grid grid-cols-3 gap-3 max-w-lg w-full mt-2">
              {[
                { emoji: "📋", text: "What happened in the last 24 hours?" },
                { emoji: "🔍", text: "How does the embedder class work?" },
                { emoji: "📁", text: "List the files in the server directory." },
              ].map((tip) => (
                <div
                  key={tip.text}
                  className="bg-[#0f0f0f] border border-[#1f1f1f] rounded-xl p-3 text-center hover:border-emerald-500/20 transition-colors cursor-default"
                >
                  <span className="text-lg">{tip.emoji}</span>
                  <p className="text-[11px] text-gray-500 mt-1.5 leading-relaxed">
                    "{tip.text}"
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Right: transcript panel */}
        <aside className="hidden lg:flex flex-col w-80 border-l border-[#1f1f1f] bg-[#050505]">
          <TranscriptPanel entries={transcript} />
        </aside>
      </main>

      {/* ── Bottom controls ────────────────────────────────────────────────── */}
      <footer className="flex items-center justify-center gap-4 px-5 py-5 border-t border-[#1f1f1f] bg-[#050505]/80 backdrop-blur-sm flex-shrink-0">
        {/* Mute */}
        <button
          onClick={handleToggleMute}
          disabled={!isCallActive}
          title={isMuted ? "Unmute" : "Mute"}
          className={`w-12 h-12 rounded-full flex items-center justify-center transition-all duration-200 border ${
            !isCallActive
              ? "border-[#1f1f1f] text-gray-700 cursor-not-allowed"
              : isMuted
              ? "border-red-500/50 bg-red-500/10 text-red-400 hover:bg-red-500/20"
              : "border-[#2a2a2a] bg-[#1a1a1a] text-gray-300 hover:border-gray-600 hover:text-white"
          }`}
        >
          {isMuted ? (
            <MicOff className="w-4 h-4" strokeWidth={2} />
          ) : (
            <Mic className="w-4 h-4" strokeWidth={2} />
          )}
        </button>

        {/* Main call button */}
        <button
          onClick={isCallActive ? handleEndCall : handleStartCall}
          disabled={isCallBusy || isLoading || (!isCallActive && !canCall)}
          title={isCallActive ? "End call" : "Start call"}
          className={`h-14 px-8 rounded-full flex items-center gap-2.5 font-semibold text-sm transition-all duration-300 border ${
            isCallActive
              ? "bg-red-500/10 border-red-500/40 text-red-400 hover:bg-red-500/20 hover:border-red-500/60"
              : isCallBusy || isLoading
              ? "bg-[#1a1a1a] border-[#2a2a2a] text-gray-500 cursor-not-allowed"
              : canCall
              ? "bg-emerald-500/10 border-emerald-500/40 text-emerald-400 hover:bg-emerald-500/20 hover:border-emerald-500/60 glow-green"
              : "bg-[#0f0f0f] border-[#1f1f1f] text-gray-600 cursor-not-allowed"
          }`}
        >
          {isLoading || isCallBusy ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" strokeWidth={2} />
              <span>{isCallBusy && callStatus === "ending" ? "Ending…" : "Connecting…"}</span>
            </>
          ) : isCallActive ? (
            <>
              <PhoneOff className="w-4 h-4" strokeWidth={2} />
              <span>End Call</span>
            </>
          ) : (
            <>
              <Phone className="w-4 h-4" strokeWidth={2} />
              <span>Start Call</span>
            </>
          )}
        </button>

        {/* Mobile transcript toggle (shows as a summary) */}
        <div className="lg:hidden flex items-center gap-1.5 text-xs text-gray-600">
          <Activity className="w-3.5 h-3.5" strokeWidth={2} />
          <span>{transcript.length} msgs</span>
        </div>
      </footer>
    </div>
  );
}
