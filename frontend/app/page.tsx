"use client";

import { useEffect, useRef, useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Voice {
  id: string;
  label: string;
  description: string;
}

interface Cut {
  id: string;
  name: string;
  label: string;
  script: string;
}

interface OutputFile {
  name: string;
  size_mb: number;
  url: string;
}

export default function Home() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [cuts, setCuts] = useState<Cut[]>([]);
  const [voice, setVoice] = useState("nova");
  const [driveUrl, setDriveUrl] = useState("");
  const [skipAssembly, setSkipAssembly] = useState(false);
  const [skipVo, setSkipVo] = useState(false);
  const [skipCaptions, setSkipCaptions] = useState(false);
  const [logs, setLogs] = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  const [scriptsDirty, setScriptsDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<"idle" | "running" | "done" | "error">("idle");
  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    fetch(`${API}/api/voices`)
      .then((r) => r.json())
      .then((d) => setVoices(d.voices))
      .catch(() => {});

    fetch(`${API}/api/scripts`)
      .then((r) => r.json())
      .then((d) => setCuts(d.cuts))
      .catch(() => {});

    fetch(`${API}/api/outputs`)
      .then((r) => r.json())
      .then((d) => setOutputs(d.files))
      .catch(() => {});
  }, []);

  useEffect(() => {
    logsEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  function updateScript(cutId: string, value: string) {
    setCuts((prev) => prev.map((c) => (c.id === cutId ? { ...c, script: value } : c)));
    setScriptsDirty(true);
  }

  async function saveScripts() {
    setSaving(true);
    await fetch(`${API}/api/scripts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scripts: cuts.map((c) => ({ cut_id: c.id, script: c.script })) }),
    });
    setSaving(false);
    setScriptsDirty(false);
  }

  async function run() {
    if (running) {
      abortRef.current?.abort();
      setRunning(false);
      setStatus("idle");
      return;
    }

    if (scriptsDirty) await saveScripts();

    setLogs([]);
    setRunning(true);
    setStatus("running");

    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(`${API}/api/run`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          voice,
          drive_url: driveUrl,
          skip_assembly: skipAssembly,
          skip_vo: skipVo,
          skip_captions: skipCaptions,
        }),
        signal: ctrl.signal,
      });

      const reader = res.body!.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split("\n");
        buf = lines.pop() || "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = JSON.parse(line.slice(6));
          if (payload.event === "log") {
            setLogs((p) => [...p, payload.message]);
          } else if (payload.event === "done") {
            setLogs((p) => [...p, "✅ " + payload.message]);
            setOutputs(payload.files || []);
            setStatus("done");
          } else if (payload.event === "error") {
            setLogs((p) => [...p, "❌ " + payload.message]);
            setStatus("error");
          } else if (payload.event === "start") {
            setLogs((p) => [...p, payload.message]);
          }
        }
      }
    } catch (e: unknown) {
      if ((e as Error).name !== "AbortError") {
        setLogs((p) => [...p, "❌ Connection error"]);
        setStatus("error");
      }
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{ display: "flex", minHeight: "100vh", background: "var(--bg-base)" }}>
      {/* Sidebar */}
      <aside style={{
        width: 220,
        flexShrink: 0,
        background: "var(--bg-surface)",
        borderRight: "1px solid var(--border)",
        display: "flex",
        flexDirection: "column",
        padding: "24px 0",
      }}>
        <div style={{ padding: "0 20px 28px" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <span style={{
              width: 28, height: 28,
              background: "var(--accent)",
              borderRadius: 6,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 14, fontWeight: 700, color: "#0d0d0d",
            }}>H</span>
            <span style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)" }}>Hookies</span>
          </div>
        </div>

        <nav style={{ flex: 1, padding: "0 12px" }}>
          {[
            { icon: "◈", label: "Generator", active: true },
            { icon: "⊞", label: "Outputs" },
          ].map((item) => (
            <div key={item.label} style={{
              display: "flex", alignItems: "center", gap: 10,
              padding: "8px 12px",
              borderRadius: 7,
              marginBottom: 2,
              cursor: "default",
              background: item.active ? "var(--bg-hover)" : "transparent",
              color: item.active ? "var(--text-primary)" : "var(--text-secondary)",
              fontSize: 13,
              fontWeight: item.active ? 500 : 400,
            }}>
              <span style={{ opacity: 0.7 }}>{item.icon}</span>
              {item.label}
            </div>
          ))}
        </nav>

        <div style={{ padding: "0 20px", marginTop: "auto" }}>
          <div style={{
            padding: "10px 12px",
            background: "var(--bg-card)",
            borderRadius: 8,
            border: "1px solid var(--border)",
          }}>
            <div style={{ fontSize: 11, color: "var(--text-muted)", marginBottom: 4 }}>Status</div>
            <div style={{
              display: "flex", alignItems: "center", gap: 6,
              fontSize: 12,
              color: status === "done" ? "var(--green)"
                : status === "error" ? "var(--red)"
                : status === "running" ? "var(--accent)"
                : "var(--text-secondary)",
            }}>
              <span style={{
                width: 6, height: 6, borderRadius: "50%",
                background: status === "done" ? "var(--green)"
                  : status === "error" ? "var(--red)"
                  : status === "running" ? "var(--accent)"
                  : "var(--text-muted)",
                animation: status === "running" ? "pulse 1.4s ease-in-out infinite" : "none",
              }} />
              {status === "idle" ? "Ready" : status === "running" ? "Running…" : status === "done" ? "Complete" : "Error"}
            </div>
          </div>
        </div>
      </aside>

      {/* Main */}
      <main style={{ flex: 1, overflowY: "auto", padding: "32px 40px" }}>
        <div style={{ maxWidth: 860, margin: "0 auto" }}>
          {/* Header */}
          <div style={{ marginBottom: 32 }}>
            <h1 style={{ fontSize: 22, fontWeight: 600, color: "var(--text-primary)", margin: 0 }}>
              Video Generator
            </h1>
            <p style={{ color: "var(--text-secondary)", margin: "6px 0 0", fontSize: 13 }}>
              Configure your cuts, write your scripts, and generate polished social clips.
            </p>
          </div>

          {/* Drive URL */}
          <Section title="Source Footage" subtitle="Paste a Google Drive folder URL (optional — leave empty to use clips in ./tmp)">
            <input
              type="url"
              placeholder="https://drive.google.com/drive/folders/..."
              value={driveUrl}
              onChange={(e) => setDriveUrl(e.target.value)}
              style={inputStyle}
            />
          </Section>

          {/* Voice Selector */}
          <Section title="Voice" subtitle="OpenAI TTS voice for voiceover narration">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              {voices.map((v) => (
                <button
                  key={v.id}
                  onClick={() => setVoice(v.id)}
                  style={{
                    ...chipStyle,
                    background: voice === v.id ? "var(--accent-dim)" : "var(--bg-card)",
                    border: `1px solid ${voice === v.id ? "var(--accent-border)" : "var(--border)"}`,
                    color: voice === v.id ? "var(--accent)" : "var(--text-secondary)",
                  }}
                >
                  <span style={{ fontWeight: 500, color: voice === v.id ? "var(--accent)" : "var(--text-primary)" }}>
                    {v.label}
                  </span>
                  <span style={{ fontSize: 11, opacity: 0.7, marginLeft: 4 }}>{v.description}</span>
                </button>
              ))}
            </div>
          </Section>

          {/* Script Cards */}
          <Section
            title="Angle Scripts"
            subtitle="Edit the voiceover script for each cut angle"
            action={
              scriptsDirty ? (
                <button onClick={saveScripts} disabled={saving} style={actionBtnStyle}>
                  {saving ? "Saving…" : "Save scripts"}
                </button>
              ) : null
            }
          >
            <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
              {cuts.map((cut, i) => (
                <div key={cut.id} style={cardStyle}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
                    <span style={{
                      width: 22, height: 22, borderRadius: 5,
                      background: "var(--accent-dim)",
                      border: "1px solid var(--accent-border)",
                      color: "var(--accent)",
                      fontSize: 11, fontWeight: 700,
                      display: "flex", alignItems: "center", justifyContent: "center",
                    }}>{i + 1}</span>
                    <span style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                      {cut.label}
                    </span>
                  </div>
                  <textarea
                    rows={4}
                    value={cut.script}
                    placeholder="Write your voiceover script here…"
                    onChange={(e) => updateScript(cut.id, e.target.value)}
                    style={textareaStyle}
                  />
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6 }}>
                    {cut.script.trim().split(/\s+/).filter(Boolean).length} words
                  </div>
                </div>
              ))}
            </div>
          </Section>

          {/* Pipeline Options */}
          <Section title="Pipeline Options" subtitle="Skip steps to speed up iteration">
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
              {[
                { label: "Skip assembly", desc: "Reuse existing cuts", val: skipAssembly, set: setSkipAssembly },
                { label: "Skip voiceover", desc: "No TTS generation", val: skipVo, set: setSkipVo },
                { label: "Skip captions", desc: "No caption burn-in", val: skipCaptions, set: setSkipCaptions },
              ].map((opt) => (
                <button
                  key={opt.label}
                  onClick={() => opt.set(!opt.val)}
                  style={{
                    ...chipStyle,
                    background: opt.val ? "var(--accent-dim)" : "var(--bg-card)",
                    border: `1px solid ${opt.val ? "var(--accent-border)" : "var(--border)"}`,
                    color: opt.val ? "var(--accent)" : "var(--text-secondary)",
                  }}
                >
                  <span style={{
                    width: 14, height: 14, borderRadius: 3,
                    border: `1.5px solid ${opt.val ? "var(--accent)" : "var(--text-muted)"}`,
                    background: opt.val ? "var(--accent)" : "transparent",
                    display: "inline-flex", alignItems: "center", justifyContent: "center",
                    fontSize: 9, color: "#0d0d0d", flexShrink: 0,
                  }}>
                    {opt.val ? "✓" : ""}
                  </span>
                  <span style={{ fontWeight: 500, color: "var(--text-primary)" }}>{opt.label}</span>
                  <span style={{ fontSize: 11, opacity: 0.65 }}>{opt.desc}</span>
                </button>
              ))}
            </div>
          </Section>

          {/* Run Button */}
          <div style={{ margin: "8px 0 32px" }}>
            <button
              onClick={run}
              style={{
                height: 42,
                padding: "0 28px",
                borderRadius: 8,
                border: "none",
                cursor: "pointer",
                fontSize: 14,
                fontWeight: 600,
                background: running ? "#2a2a2a" : "var(--accent)",
                color: running ? "var(--text-secondary)" : "#0d0d0d",
                transition: "background 0.2s, color 0.2s",
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}
            >
              {running ? <><Spinner /> Stop pipeline</> : "Generate cuts"}
            </button>
          </div>

          {/* Log Console */}
          {logs.length > 0 && (
            <Section title="Pipeline Log" subtitle="">
              <div style={{
                background: "#0a0a0a",
                border: "1px solid var(--border)",
                borderRadius: 8,
                padding: "14px 16px",
                fontFamily: "ui-monospace, 'JetBrains Mono', monospace",
                fontSize: 12,
                color: "#aaa",
                maxHeight: 320,
                overflowY: "auto",
                lineHeight: 1.7,
              }}>
                {logs.map((line, i) => (
                  <div key={i} style={{
                    color: line.startsWith("✅") ? "var(--green)"
                      : line.startsWith("❌") ? "var(--red)"
                      : line.startsWith("⚠") ? "var(--accent)"
                      : "#aaa",
                  }}>
                    {line}
                  </div>
                ))}
                <div ref={logsEndRef} />
              </div>
            </Section>
          )}

          {/* Outputs */}
          {outputs.length > 0 && (
            <Section title="Output Files" subtitle={`${outputs.length} files ready`}>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {outputs.map((file) => (
                  <div key={file.name} style={{
                    display: "flex", alignItems: "center", justifyContent: "space-between",
                    background: "var(--bg-card)",
                    border: "1px solid var(--border)",
                    borderRadius: 8,
                    padding: "12px 16px",
                  }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <span style={{ fontSize: 16 }}>🎬</span>
                      <div>
                        <div style={{ fontSize: 13, fontWeight: 500, color: "var(--text-primary)" }}>
                          {file.name}
                        </div>
                        <div style={{ fontSize: 11, color: "var(--text-muted)" }}>{file.size_mb} MB</div>
                      </div>
                    </div>
                    <a
                      href={`${API}${file.url}`}
                      download={file.name}
                      style={{
                        padding: "6px 14px",
                        borderRadius: 6,
                        border: "1px solid var(--border)",
                        background: "var(--bg-hover)",
                        color: "var(--text-primary)",
                        fontSize: 12,
                        fontWeight: 500,
                        textDecoration: "none",
                        cursor: "pointer",
                      }}
                    >
                      Download
                    </a>
                  </div>
                ))}
              </div>
            </Section>
          )}
        </div>
      </main>

      <style>{`
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

function Section({
  title,
  subtitle,
  children,
  action,
}: {
  title: string;
  subtitle: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div style={{ marginBottom: 28 }}>
      <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", marginBottom: 10 }}>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>{title}</div>
          {subtitle && <div style={{ fontSize: 12, color: "var(--text-muted)" }}>{subtitle}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Spinner() {
  return (
    <span style={{
      display: "inline-block",
      width: 14, height: 14,
      border: "2px solid #555",
      borderTopColor: "var(--accent)",
      borderRadius: "50%",
      animation: "spin 0.7s linear infinite",
    }} />
  );
}

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "9px 12px",
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 7,
  color: "var(--text-primary)",
  fontSize: 13,
  outline: "none",
};

const textareaStyle: React.CSSProperties = {
  width: "100%",
  padding: "10px 12px",
  background: "var(--bg-base)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  color: "var(--text-primary)",
  fontSize: 13,
  resize: "vertical",
  outline: "none",
  lineHeight: 1.6,
};

const cardStyle: React.CSSProperties = {
  padding: "16px",
  background: "var(--bg-card)",
  border: "1px solid var(--border)",
  borderRadius: 10,
};

const chipStyle: React.CSSProperties = {
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "7px 12px",
  borderRadius: 7,
  cursor: "pointer",
  fontSize: 12,
};

const actionBtnStyle: React.CSSProperties = {
  padding: "5px 12px",
  borderRadius: 6,
  border: "1px solid var(--accent-border)",
  background: "var(--accent-dim)",
  color: "var(--accent)",
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
};
