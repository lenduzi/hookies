"use client";

import { useEffect, useRef, useState, useCallback } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Voice       { id: string; label: string; description: string }
interface ProjectMeta { id: string; name: string; brief: string; angle?: string; angles?: string[]; drive_url: string; cut_count: number; output_count: number }
interface Cut         { id: string; name: string; label: string; hook: string; vibe: string; assigned_angle: string; script: string; has_clips: boolean }
interface OutputFile  { name: string; size_mb: number; url: string }
interface Variant     { label: string; script: string }
interface ClipInfo    { filename: string; duration: number; size_mb: number; thumbnail_url: string }
interface TrimPoint   { start: number; end: number }
interface PlanCut     { id: string; name: string; label: string; clips: string[]; trim: Record<string, TrimPoint>; transition: string }

// ── Constants ─────────────────────────────────────────────────────────────────

const ANGLE_PILLS = [
  "Date night idea",
  "Things to do in [city]",
  "Hidden gem",
  "Underrated activity",
  "Only locals know",
  "Weekend activity",
  "POV you discovered",
  "Behind the scenes",
];

const CTA_PILLS = [
  "Link in bio",
  "DM me",
  "Comment below",
  "Save this",
  "Follow for more",
  "Tag a friend",
];

// ── Home ──────────────────────────────────────────────────────────────────────

export default function Home() {
  // meta
  const [voices,   setVoices]   = useState<Voice[]>([]);
  const [projects, setProjects] = useState<ProjectMeta[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  // scripts
  const [cuts,         setCuts]         = useState<Cut[]>([]);
  const [scriptsDirty, setScriptsDirty] = useState(false);
  const [saving,       setSaving]       = useState(false);
  // clip plan
  const [clips,       setClips]       = useState<ClipInfo[]>([]);
  const [planCuts,    setPlanCuts]    = useState<PlanCut[]>([]);
  const [planDirty,   setPlanDirty]   = useState(false);
  const [savingPlan,  setSavingPlan]  = useState(false);
  const [loadingClips,setLoadingClips]= useState(false);
  // AI Edit Plan + Drive sync
  const [aiPlanning,  setAiPlanning]  = useState(false);
  const [aiPlanLogs,  setAiPlanLogs]  = useState<string[]>([]);
  const [syncingDrive, setSyncingDrive] = useState(false);
  // pipeline
  const [voice,          setVoice]          = useState("FGY2WhTYpPnrIDTdsKH5"); // Laura (ElevenLabs default)
  const [captionStyle,   setCaptionStyle]   = useState("classic");
  const [skipAssembly,   setSkipAssembly]   = useState(false);
  const [skipVo,         setSkipVo]         = useState(false);
  const [skipCaptions,   setSkipCaptions]   = useState(false);
  const [skipDownload,   setSkipDownload]   = useState(false);
  const [logs,    setLogs]    = useState<string[]>([]);
  const [running, setRunning] = useState(false);
  const [status,  setStatus]  = useState<"idle"|"running"|"done"|"error">("idle");
  const [outputs, setOutputs] = useState<OutputFile[]>([]);
  // modals / generate
  const [showNewProject,   setShowNewProject]   = useState(false);
  const [generatingCut,    setGeneratingCut]    = useState<string|null>(null);
  const [variants,         setVariants]         = useState<{cutId:string; items:Variant[]}|null>(null);
  const [generatingAngles, setGeneratingAngles] = useState(false);
  const [angleContents,    setAngleContents]    = useState<string[]>([]);  // up to 3, one per cut
  const [anglePlatform,    setAnglePlatform]    = useState("");
  const [angleCta,         setAngleCta]         = useState("");
  const [angleLanguage,    setAngleLanguage]    = useState("auto");
  const [angleExtra,       setAngleExtra]       = useState("");

  const logsEndRef = useRef<HTMLDivElement>(null);
  const abortRef   = useRef<AbortController|null>(null);

  // ── Loaders ─────────────────────────────────────────────────────────────────

  const loadProjects = useCallback(async () => {
    const d = await fetch(`${API}/api/projects`).then(r=>r.json()).catch(()=>({projects:[]}));
    setProjects(d.projects||[]);
    return d.projects as ProjectMeta[];
  }, []);

  const loadClips = useCallback(async (id: string) => {
    setLoadingClips(true);
    const d = await fetch(`${API}/api/projects/${id}/clips`).then(r=>r.json()).catch(()=>({clips:[]}));
    setClips(d.clips||[]);
    setLoadingClips(false);
  }, []);

  const loadProject = useCallback(async (id: string) => {
    const [scripts, projectData, outputs] = await Promise.all([
      fetch(`${API}/api/projects/${id}/scripts`).then(r=>r.json()).catch(()=>({cuts:[]})),
      fetch(`${API}/api/projects/${id}`).then(r=>r.json()).catch(()=>({plan:{cuts:[]}})),
      fetch(`${API}/api/projects/${id}/outputs`).then(r=>r.json()).catch(()=>({files:[]})),
    ]);
    setCuts(scripts.cuts||[]);
    setOutputs(outputs.files||[]);
    // Populate angles from meta (prefer multi-angle list, fall back to single angle)
    const metaAngles: string[] = projectData.project?.angles || (projectData.project?.angle ? [projectData.project.angle] : []);
    setAngleContents(metaAngles);
    const rawCuts: PlanCut[] = (projectData.plan?.cuts||[]).map((c: Record<string,unknown>) => ({
      id: c.id as string,
      name: c.name as string,
      label: (c.label||c.name) as string,
      clips: (c.clips||[]) as string[],
      trim:  (c.trim||{}) as Record<string,TrimPoint>,
      transition: (c.transition||"cut") as string,
    }));
    setPlanCuts(rawCuts);
    setScriptsDirty(false);
    setPlanDirty(false);
    setVariants(null);
    setLogs([]);
    setStatus("idle");
    loadClips(id);
  }, [loadClips]);

  useEffect(() => {
    fetch(`${API}/api/voices`).then(r=>r.json()).then(d=>setVoices(d.voices)).catch(()=>{});
    loadProjects().then(ps => {
      if (ps.length > 0) { setActiveId(ps[0].id); loadProject(ps[0].id); }
    });
  }, [loadProjects, loadProject]);

  useEffect(() => { logsEndRef.current?.scrollIntoView({behavior:"smooth"}); }, [logs]);

  // ── Actions ──────────────────────────────────────────────────────────────────

  function switchProject(id: string) {
    if (id === activeId) return;
    setActiveId(id);
    setAngleContents([]); // cleared; loadProject will repopulate from meta
    loadProject(id);
  }

  function updateScript(cutId: string, value: string) {
    setCuts(prev => prev.map(c => c.id===cutId ? {...c,script:value} : c));
    setScriptsDirty(true);
  }

  async function saveScripts() {
    if (!activeId) return;
    setSaving(true);
    await fetch(`${API}/api/projects/${activeId}/scripts`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({scripts: cuts.map(c=>({cut_id:c.id,script:c.script}))}),
    });
    setSaving(false); setScriptsDirty(false);
  }

  async function savePlan() {
    if (!activeId) return;
    setSavingPlan(true);
    const d = await fetch(`${API}/api/projects/${activeId}/plan`, {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({cuts: planCuts}),
    }).then(r=>r.json()).catch(()=>({}));
    if (d.cuts) setCuts(d.cuts);
    setSavingPlan(false); setPlanDirty(false);
    loadProjects();
  }

  async function runSyncDrive() {
    if (!activeId || syncingDrive) return;
    setSyncingDrive(true);
    setAiPlanLogs(["Connecting to Google Drive…"]);
    try {
      const res = await fetch(`${API}/api/projects/${activeId}/sync-drive`, {method:"POST"});
      if (!res.body) throw new Error("No stream");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream:true});
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;
          try {
            const msg = JSON.parse(line);
            if (msg.event === "progress") setAiPlanLogs(prev=>[...prev, msg.message]);
            if (msg.event === "done") {
              setAiPlanLogs(prev=>[...prev, msg.message]);
              await loadClips(activeId);
            }
            if (msg.event === "error") setAiPlanLogs(prev=>[...prev, `Error: ${msg.message}`]);
          } catch {}
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setAiPlanLogs(prev=>[...prev, `Failed: ${msg}`]);
    } finally {
      setSyncingDrive(false);
    }
  }

  async function runAiPlan() {
    if (!activeId || aiPlanning) return;
    setAiPlanning(true);
    setAiPlanLogs(["Starting AI analysis…"]);
    try {
      const res = await fetch(`${API}/api/projects/${activeId}/analyze-and-plan`, {method:"POST"});
      if (!res.body) throw new Error("No stream");
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const {done, value} = await reader.read();
        if (done) break;
        buf += decoder.decode(value, {stream:true});
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const part of parts) {
          const line = part.replace(/^data: /, "").trim();
          if (!line) continue;
          try {
            const msg = JSON.parse(line);
            if (msg.event === "progress") setAiPlanLogs(prev=>[...prev, msg.message]);
            if (msg.event === "done") {
              setAiPlanLogs(prev=>[...prev, "Done! Plan updated."]);
              await loadProject(activeId);
            }
            if (msg.event === "error") setAiPlanLogs(prev=>[...prev, `Error: ${msg.message}`]);
          } catch {}
        }
      }
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setAiPlanLogs(prev=>[...prev, `Failed: ${msg}`]);
    } finally {
      setAiPlanning(false);
    }
  }

  function updatePlanCut(cutId: string, updater: (c: PlanCut) => PlanCut) {
    setPlanCuts(prev => prev.map(c => c.id===cutId ? updater(c) : c));
    setPlanDirty(true);
  }

  function addClipToCut(cutId: string, filename: string) {
    updatePlanCut(cutId, c => {
      if (c.clips.includes(filename)) return c;
      const clip = clips.find(cl=>cl.filename===filename);
      const end = clip ? clip.duration : 5;
      return {...c, clips:[...c.clips,filename], trim:{...c.trim,[filename]:{start:0,end:end}}};
    });
  }

  function removeClipFromCut(cutId: string, filename: string) {
    updatePlanCut(cutId, c => {
      const trim = {...c.trim}; delete trim[filename];
      return {...c, clips:c.clips.filter(f=>f!==filename), trim};
    });
  }

  function moveClip(cutId: string, from: number, to: number) {
    updatePlanCut(cutId, c => {
      const clips = [...c.clips];
      const [item] = clips.splice(from, 1);
      clips.splice(to, 0, item);
      return {...c, clips};
    });
  }

  function updateTrim(cutId: string, filename: string, field: "start"|"end", value: number) {
    updatePlanCut(cutId, c => ({
      ...c, trim:{...c.trim,[filename]:{...c.trim[filename],[field]:value}}
    }));
  }

  async function generateAngles() {
    if (!activeId) return;
    setGeneratingAngles(true);
    try {
      const d = await fetch(`${API}/api/projects/${activeId}/generate-angles`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          angles: angleContents,
          platform: anglePlatform,
          cta: angleCta,
          language: angleLanguage,
          extra: angleExtra,
        }),
      }).then(r=>r.json());
      if (d.cuts) {
        setCuts(d.cuts);
        // Sync labels into planCuts
        setPlanCuts(prev => prev.map((pc,i) => {
          const nc = d.cuts[i];
          return nc ? {...pc, name:nc.name, label:nc.label} : pc;
        }));
        setScriptsDirty(false);
      }
    } catch { alert("Angle generation failed — check API key"); }
    finally { setGeneratingAngles(false); }
  }

  async function generateVariants(cutId: string) {
    if (!activeId) return;
    setGeneratingCut(cutId); setVariants(null);
    try {
      const d = await fetch(`${API}/api/projects/${activeId}/generate`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({cut_id:cutId}),
      }).then(r=>r.json());
      setVariants({cutId, items:d.variants||[]});
    } catch { alert("Generation failed — check API key"); }
    finally { setGeneratingCut(null); }
  }

  function pickVariant(cutId: string, script: string) { updateScript(cutId,script); setVariants(null); }

  async function run() {
    if (!activeId) return;
    if (running) { abortRef.current?.abort(); setRunning(false); setStatus("idle"); return; }
    if (scriptsDirty) await saveScripts();
    if (planDirty) await savePlan();
    setLogs([]); setRunning(true); setStatus("running");
    const ctrl = new AbortController(); abortRef.current = ctrl;
    try {
      const res = await fetch(`${API}/api/projects/${activeId}/run`, {
        method:"POST", headers:{"Content-Type":"application/json"},
        body: JSON.stringify({
          voice,
          skip_assembly: skipAssembly,
          skip_vo: skipVo,
          skip_captions: skipCaptions,
          skip_download: skipDownload,
          caption_style: captionStyle,
        }),
        signal: ctrl.signal,
      });
      const reader = res.body!.getReader(); const decoder = new TextDecoder(); let buf="";
      while (true) {
        const {done,value} = await reader.read(); if (done) break;
        buf += decoder.decode(value,{stream:true});
        const lines = buf.split("\n"); buf = lines.pop()||"";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const p = JSON.parse(line.slice(6));
          if (p.event==="log")   setLogs(prev=>[...prev,p.message]);
          else if (p.event==="done")  { setLogs(prev=>[...prev,"✅ "+p.message]); setOutputs(p.files||[]); setStatus("done"); loadProjects(); }
          else if (p.event==="error") { setLogs(prev=>[...prev,"❌ "+p.message]); setStatus("error"); }
          else if (p.event==="start") { setLogs(prev=>[...prev,p.message]); }
        }
      }
    } catch (e:unknown) {
      if ((e as Error).name!=="AbortError") { setLogs(p=>[...p,"❌ Connection error"]); setStatus("error"); }
    } finally { setRunning(false); }
  }

  // ── Render ───────────────────────────────────────────────────────────────────

  const activeProject = projects.find(p=>p.id===activeId);

  return (
    <div style={{display:"flex",minHeight:"100vh",background:"var(--bg-base)"}}>

      {/* ── Sidebar ── */}
      <aside style={{width:240,flexShrink:0,background:"var(--bg-surface)",borderRight:"1px solid var(--border)",display:"flex",flexDirection:"column",padding:"20px 0"}}>
        <div style={{padding:"0 18px 20px",display:"flex",alignItems:"center",gap:10}}>
          <span style={{width:28,height:28,background:"var(--accent)",borderRadius:6,display:"flex",alignItems:"center",justifyContent:"center",fontSize:14,fontWeight:700,color:"#0d0d0d"}}>H</span>
          <span style={{fontSize:15,fontWeight:600}}>Hookies</span>
        </div>
        <div style={{padding:"0 18px 8px",display:"flex",alignItems:"center",justifyContent:"space-between"}}>
          <span style={{fontSize:11,fontWeight:600,color:"var(--text-muted)",textTransform:"uppercase",letterSpacing:"0.06em"}}>Projects</span>
          <button onClick={()=>setShowNewProject(true)} style={{width:22,height:22,borderRadius:5,border:"1px solid var(--border)",background:"var(--bg-card)",color:"var(--text-secondary)",cursor:"pointer",fontSize:16,display:"flex",alignItems:"center",justifyContent:"center"}}>+</button>
        </div>
        <div style={{flex:1,overflowY:"auto",padding:"0 10px"}}>
          {projects.length===0 && <div style={{padding:"8px 12px",fontSize:12,color:"var(--text-muted)"}}>No projects yet</div>}
          {projects.map(p=>(
            <div key={p.id} onClick={()=>switchProject(p.id)} style={{padding:"8px 10px",borderRadius:7,marginBottom:2,cursor:"pointer",background:activeId===p.id?"var(--bg-hover)":"transparent",transition:"background 0.15s"}}>
              <div style={{fontSize:13,fontWeight:activeId===p.id?500:400,color:activeId===p.id?"var(--text-primary)":"var(--text-secondary)"}}>{p.name}</div>
              <div style={{fontSize:11,color:"var(--text-muted)",marginTop:1}}>{p.cut_count} cuts · {p.output_count} videos</div>
            </div>
          ))}
        </div>
        <div style={{padding:"12px 18px 0"}}>
          <div style={{padding:"9px 12px",background:"var(--bg-card)",borderRadius:8,border:"1px solid var(--border)"}}>
            <div style={{fontSize:11,color:"var(--text-muted)",marginBottom:3}}>Pipeline</div>
            <div style={{display:"flex",alignItems:"center",gap:6,fontSize:12,color:status==="done"?"var(--green)":status==="error"?"var(--red)":status==="running"?"var(--accent)":"var(--text-secondary)"}}>
              <span style={{width:6,height:6,borderRadius:"50%",background:status==="done"?"var(--green)":status==="error"?"var(--red)":status==="running"?"var(--accent)":"var(--text-muted)",animation:status==="running"?"pulse 1.4s ease-in-out infinite":"none"}}/>
              {status==="idle"?"Ready":status==="running"?"Running…":status==="done"?"Complete":"Error"}
            </div>
          </div>
        </div>
      </aside>

      {/* ── Main ── */}
      <main style={{flex:1,overflowY:"auto",padding:"32px 40px"}}>
        {!activeProject ? <EmptyState onNew={()=>setShowNewProject(true)}/> : (
          <div style={{maxWidth:900,margin:"0 auto"}}>

            {/* Header */}
            <div style={{marginBottom:28}}>
              <h1 style={{fontSize:22,fontWeight:600,margin:0}}>{activeProject.name}</h1>
              {activeProject.brief && <p style={{color:"var(--text-secondary)",margin:"6px 0 0",fontSize:13,maxWidth:580,lineHeight:1.6}}>{activeProject.brief.slice(0,160)}{activeProject.brief.length>160?"…":""}</p>}
            </div>

            {/* Generate Angles */}
            <Section title="Generate Angles" subtitle="Let Claude propose 3 distinct video concepts from your project brief"
              action={<button onClick={generateAngles} disabled={generatingAngles} style={{display:"flex",alignItems:"center",gap:6,padding:"6px 14px",borderRadius:7,border:"none",background:generatingAngles?"var(--bg-hover)":"var(--accent)",color:generatingAngles?"var(--text-secondary)":"#0d0d0d",fontSize:12,fontWeight:600,cursor:"pointer"}}>
                {generatingAngles?<><Spinner size={11}/> Generating…</>:"✦ Generate angles"}
              </button>}
            >
              <div style={{display:"flex",flexDirection:"column",gap:10}}>

                {/* Content angles — multi-select, up to 3 */}
                <div style={{display:"flex",alignItems:"flex-start",gap:10}}>
                  <div style={{width:130,fontSize:12,color:"var(--text-muted)",flexShrink:0,paddingTop:4}}>Content angles</div>
                  <AngleSelector value={angleContents} onChange={setAngleContents}/>
                </div>

                {/* Platform */}
                <div style={{display:"flex",alignItems:"center",gap:10}}>
                  <div style={{width:130,fontSize:12,color:"var(--text-muted)",flexShrink:0}}>Platform</div>
                  <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
                    {["TikTok / Reels","YouTube Shorts","Both"].map(opt=>(
                      <button key={opt} onClick={()=>setAnglePlatform(anglePlatform===opt?"":opt)} style={{padding:"4px 10px",borderRadius:5,fontSize:12,cursor:"pointer",background:anglePlatform===opt?"var(--accent-dim)":"var(--bg-card)",border:`1px solid ${anglePlatform===opt?"var(--accent-border)":"var(--border)"}`,color:anglePlatform===opt?"var(--accent)":"var(--text-secondary)"}}>{opt}</button>
                    ))}
                  </div>
                </div>

                {/* Language */}
                <div style={{display:"flex",alignItems:"center",gap:10}}>
                  <div style={{width:130,fontSize:12,color:"var(--text-muted)",flexShrink:0}}>Script language</div>
                  <div style={{display:"flex",gap:6}}>
                    {[{val:"auto",label:"Auto (match brief)"},{val:"en",label:"English"},{val:"de",label:"Deutsch"}].map(opt=>(
                      <button key={opt.val} onClick={()=>setAngleLanguage(opt.val)} style={{padding:"4px 10px",borderRadius:5,fontSize:12,cursor:"pointer",background:angleLanguage===opt.val?"var(--accent-dim)":"var(--bg-card)",border:`1px solid ${angleLanguage===opt.val?"var(--accent-border)":"var(--border)"}`,color:angleLanguage===opt.val?"var(--accent)":"var(--text-secondary)"}}>{opt.label}</button>
                    ))}
                  </div>
                </div>

                {/* CTA — pills + free-text input */}
                <PillInputRow
                  label="CTA style"
                  pills={CTA_PILLS}
                  value={angleCta}
                  onChange={setAngleCta}
                  placeholder="Custom CTA — e.g. 'You HAVE to try this!'"
                />

                {/* Extra notes */}
                <div style={{display:"flex",alignItems:"center",gap:10}}>
                  <div style={{width:130,fontSize:12,color:"var(--text-muted)",flexShrink:0}}>Extra notes</div>
                  <input value={angleExtra} onChange={e=>setAngleExtra(e.target.value)} placeholder="Optional — e.g. 'focus on the blowtorch moment'" style={{...inputStyle,flex:1}}/>
                </div>

              </div>
            </Section>

            {/* Clip Plan Editor */}
            <Section title="Clip Plan" subtitle="Assign footage to each cut and set trim points"
              action={
                <div style={{display:"flex",gap:8,alignItems:"center"}}>
                  {projects.find(p=>p.id===activeId)?.drive_url && (
                    <button onClick={runSyncDrive} disabled={syncingDrive||aiPlanning} style={actionBtnStyle}>
                      {syncingDrive ? "Syncing…" : "⬇ Sync Drive"}
                    </button>
                  )}
                  <button onClick={runAiPlan} disabled={aiPlanning||syncingDrive} style={actionBtnStyle}>
                    {aiPlanning ? "Planning…" : "✦ AI Edit Plan"}
                  </button>
                  {planDirty && <button onClick={savePlan} disabled={savingPlan} style={actionBtnStyle}>{savingPlan?"Saving…":"Save plan"}</button>}
                </div>
              }
            >
              <ClipPlanEditor
                projectId={activeId!}
                planCuts={planCuts}
                clips={clips}
                loadingClips={loadingClips}
                driveUrl={projects.find(p=>p.id===activeId)?.drive_url}
                onAddClip={addClipToCut}
                onRemoveClip={removeClipFromCut}
                onMoveClip={moveClip}
                onUpdateTrim={updateTrim}
                onTransitionChange={(cutId,t)=>updatePlanCut(cutId,c=>({...c,transition:t}))}
              />
              {aiPlanLogs.length > 0 && (
                <div style={{marginTop:10,padding:"10px 14px",background:"var(--bg-surface)",border:"1px solid var(--border)",borderRadius:8,fontFamily:"monospace",fontSize:11,color:"var(--text-secondary)",maxHeight:160,overflowY:"auto"}}>
                  {aiPlanLogs.map((l,i)=>(
                    <div key={i} style={{padding:"1px 0",color: l.startsWith("Error") ? "var(--error,#f87171)" : l.startsWith("Done") ? "var(--accent)" : "inherit"}}>{l}</div>
                  ))}
                </div>
              )}
            </Section>

            {/* Voice */}
            <Section title="Voice" subtitle="OpenAI TTS voice for narration">
              <div style={{display:"flex",gap:8,flexWrap:"wrap"}}>
                {voices.map(v=>(
                  <button key={v.id} onClick={()=>setVoice(v.id)} style={{...chipStyle,background:voice===v.id?"var(--accent-dim)":"var(--bg-card)",border:`1px solid ${voice===v.id?"var(--accent-border)":"var(--border)"}`}}>
                    <span style={{fontWeight:500,color:voice===v.id?"var(--accent)":"var(--text-primary)"}}>{v.label}</span>
                    <span style={{fontSize:11,color:"var(--text-muted)",marginLeft:2}}>{v.description}</span>
                  </button>
                ))}
              </div>
            </Section>

            {/* Angle Scripts */}
            <Section title="Angle Scripts" subtitle="Edit or generate a voiceover script for each cut"
              action={scriptsDirty ? <button onClick={saveScripts} disabled={saving} style={actionBtnStyle}>{saving?"Saving…":"Save scripts"}</button> : null}
            >
              <div style={{display:"flex",flexDirection:"column",gap:16}}>
                {cuts.map((cut,i)=>(
                  <div key={cut.id}>
                    <div style={cardStyle}>
                      <div style={{display:"flex",alignItems:"flex-start",justifyContent:"space-between",marginBottom:10}}>
                        <div style={{display:"flex",alignItems:"center",gap:8}}>
                          <span style={{width:22,height:22,borderRadius:5,flexShrink:0,background:"var(--accent-dim)",border:"1px solid var(--accent-border)",color:"var(--accent)",fontSize:11,fontWeight:700,display:"flex",alignItems:"center",justifyContent:"center"}}>{i+1}</span>
                          <div>
                            <div style={{fontSize:13,fontWeight:500}}>{cut.label}</div>
                            {cut.assigned_angle && (
                              <div style={{display:"inline-flex",alignItems:"center",gap:4,marginTop:3,padding:"2px 7px",borderRadius:4,background:"var(--accent-dim)",border:"1px solid var(--accent-border)"}}>
                                <span style={{fontSize:10,fontWeight:700,color:"var(--accent)"}}>ANGLE</span>
                                <span style={{fontSize:11,color:"var(--text-primary)"}}>{cut.assigned_angle}</span>
                              </div>
                            )}
                            {cut.vibe && <div style={{fontSize:11,color:"var(--text-muted)",marginTop:3}}>{cut.vibe}</div>}
                          </div>
                        </div>
                        <button onClick={()=>generateVariants(cut.id)} disabled={generatingCut!==null} style={{display:"flex",alignItems:"center",gap:5,padding:"5px 10px",borderRadius:6,border:"1px solid var(--border)",background:"var(--bg-hover)",color:"var(--text-secondary)",fontSize:12,cursor:"pointer"}}>
                          {generatingCut===cut.id?<><Spinner size={11}/> Generating…</>:"✦ Generate"}
                        </button>
                      </div>
                      <textarea rows={4} value={cut.script} placeholder="Write your voiceover script here, or click Generate…" onChange={e=>updateScript(cut.id,e.target.value)} style={textareaStyle}/>
                      <div style={{fontSize:11,color:"var(--text-muted)",marginTop:5}}>{cut.script.trim().split(/\s+/).filter(Boolean).length} words</div>
                    </div>
                    {variants?.cutId===cut.id && (
                      <div style={{marginTop:8,padding:14,background:"var(--bg-surface)",border:"1px solid var(--accent-border)",borderRadius:8}}>
                        <div style={{fontSize:12,fontWeight:600,color:"var(--accent)",marginBottom:10}}>✦ Choose a variant</div>
                        <div style={{display:"flex",flexDirection:"column",gap:8}}>
                          {variants.items.map((v,vi)=>(
                            <div key={vi} onClick={()=>pickVariant(cut.id,v.script)} style={{padding:"10px 12px",background:"var(--bg-card)",border:"1px solid var(--border)",borderRadius:7,cursor:"pointer"}}>
                              <div style={{fontSize:11,fontWeight:600,color:"var(--text-muted)",marginBottom:4}}>{v.label}</div>
                              <div style={{fontSize:13,lineHeight:1.6}}>{v.script}</div>
                              <div style={{fontSize:11,color:"var(--accent)",marginTop:6}}>Click to use →</div>
                            </div>
                          ))}
                        </div>
                        <button onClick={()=>setVariants(null)} style={{marginTop:8,fontSize:12,color:"var(--text-muted)",background:"none",border:"none",cursor:"pointer",padding:0}}>Dismiss</button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Section>

            {/* Pipeline Options */}
            <Section title="Pipeline Options" subtitle="Skip steps to speed up iteration">
              <div style={{display:"flex",flexDirection:"column",gap:12}}>
                {/* Skip toggles */}
                <div style={{display:"flex",gap:10,flexWrap:"wrap"}}>
                  {[
                    {label:"Skip download", desc:"Reuse cached clips",    val:skipDownload,  set:setSkipDownload},
                    {label:"Skip assembly", desc:"Reuse existing cuts",   val:skipAssembly,  set:setSkipAssembly},
                    {label:"Skip voiceover",desc:"No TTS",                val:skipVo,        set:setSkipVo},
                    {label:"Skip captions", desc:"No burn-in",            val:skipCaptions,  set:setSkipCaptions},
                  ].map(opt=>(
                    <button key={opt.label} onClick={()=>opt.set(!opt.val)} style={{...chipStyle,background:opt.val?"var(--accent-dim)":"var(--bg-card)",border:`1px solid ${opt.val?"var(--accent-border)":"var(--border)"}`}}>
                      <Checkbox checked={opt.val}/>
                      <span style={{fontWeight:500,color:"var(--text-primary)"}}>{opt.label}</span>
                      <span style={{fontSize:11,color:"var(--text-muted)"}}>{opt.desc}</span>
                    </button>
                  ))}
                </div>
                {/* Caption style */}
                {!skipCaptions && (
                  <div style={{display:"flex",alignItems:"center",gap:10}}>
                    <div style={{fontSize:12,color:"var(--text-muted)",width:110,flexShrink:0}}>Caption style</div>
                    <div style={{display:"flex",gap:6}}>
                      {[
                        {val:"classic", label:"Classic", desc:"Bold + golden highlights"},
                        {val:"pill",    label:"Pill",    desc:"Dark background box"},
                      ].map(opt=>(
                        <button key={opt.val} onClick={()=>setCaptionStyle(opt.val)} style={{...chipStyle,background:captionStyle===opt.val?"var(--accent-dim)":"var(--bg-card)",border:`1px solid ${captionStyle===opt.val?"var(--accent-border)":"var(--border)"}`}}>
                          <span style={{fontWeight:500,color:captionStyle===opt.val?"var(--accent)":"var(--text-primary)"}}>{opt.label}</span>
                          <span style={{fontSize:11,color:"var(--text-muted)"}}>{opt.desc}</span>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </Section>

            {/* Run */}
            {(()=>{
              const hasClips = cuts.some(c=>c.has_clips);
              return (
                <div style={{margin:"4px 0 28px"}}>
                  {!hasClips && !skipAssembly ? (
                    <div style={{padding:"12px 16px",borderRadius:8,background:"var(--bg-card)",border:"1px solid var(--border)",fontSize:13,color:"var(--text-secondary)",lineHeight:1.6}}>
                      <span style={{color:"var(--accent)",fontWeight:600}}>No clips configured</span>{" "}— assign footage in the Clip Plan above, then save.{" "}
                      Enable <strong style={{color:"var(--text-primary)"}}>Skip assembly</strong> to regenerate voiceovers for existing cuts.
                    </div>
                  ) : (
                    <button onClick={run} style={{height:42,padding:"0 28px",borderRadius:8,border:"none",cursor:"pointer",fontSize:14,fontWeight:600,background:running?"var(--bg-hover)":"var(--accent)",color:running?"var(--text-secondary)":"#0d0d0d",display:"flex",alignItems:"center",gap:8,transition:"background 0.2s"}}>
                      {running?<><Spinner/> Stop pipeline</>:"Generate cuts"}
                    </button>
                  )}
                </div>
              );
            })()}

            {/* Log */}
            {logs.length>0 && (
              <Section title="Pipeline Log" subtitle="">
                <div style={{background:"#080808",border:"1px solid var(--border)",borderRadius:8,padding:"12px 14px",fontFamily:"ui-monospace,monospace",fontSize:12,color:"#aaa",maxHeight:300,overflowY:"auto",lineHeight:1.7}}>
                  {logs.map((line,i)=>(
                    <div key={i} style={{color:line.startsWith("✅")?"var(--green)":line.startsWith("❌")?"var(--red)":line.startsWith("⚠")?"var(--accent)":"#aaa"}}>{line}</div>
                  ))}
                  <div ref={logsEndRef}/>
                </div>
              </Section>
            )}

            {/* Outputs */}
            {outputs.length>0 && (
              <Section title="Output Files" subtitle={`${outputs.length} files ready`}>
                <div style={{display:"flex",flexDirection:"column",gap:8}}>
                  {outputs.map(file=>(
                    <div key={file.name} style={{display:"flex",alignItems:"center",justifyContent:"space-between",background:"var(--bg-card)",border:"1px solid var(--border)",borderRadius:8,padding:"11px 14px"}}>
                      <div style={{display:"flex",alignItems:"center",gap:10}}>
                        <span style={{fontSize:15}}>🎬</span>
                        <div>
                          <div style={{fontSize:13,fontWeight:500}}>{file.name}</div>
                          <div style={{fontSize:11,color:"var(--text-muted)"}}>{file.size_mb} MB</div>
                        </div>
                      </div>
                      <a href={`${API}${file.url}`} download={file.name} style={{padding:"5px 12px",borderRadius:6,border:"1px solid var(--border)",background:"var(--bg-hover)",color:"var(--text-primary)",fontSize:12,fontWeight:500,textDecoration:"none"}}>Download</a>
                    </div>
                  ))}
                </div>
              </Section>
            )}
          </div>
        )}
      </main>

      {showNewProject && (
        <NewProjectModal onClose={()=>setShowNewProject(false)} onCreate={async(name,brief,angle,driveUrl)=>{
          const d = await fetch(`${API}/api/projects`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,brief,angle,drive_url:driveUrl})}).then(r=>r.json());
          if (angle) setAngleContents([angle]); // pre-populate angle selector from modal
          setShowNewProject(false);
          const ps = await loadProjects();
          const newId = d.project?.id||ps[ps.length-1]?.id;
          if (newId) { setActiveId(newId); loadProject(newId); }
        }}/>
      )}

      <style>{`
        @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }
        @keyframes spin   { to{transform:rotate(360deg)} }
      `}</style>
    </div>
  );
}

// ── AngleSelector ─────────────────────────────────────────────────────────────
// Multi-select angle picker. Up to 3 angles, one per cut.
// Clicking a pill toggles it. Selecting 3 disables remaining pills.
// Custom angles can be typed and added with Enter or the + button.

function AngleSelector({value, onChange}: {value: string[]; onChange: (v: string[]) => void}) {
  const [custom, setCustom] = useState("");

  function toggle(opt: string) {
    if (value.includes(opt)) {
      onChange(value.filter(a => a !== opt));
    } else if (value.length < 3) {
      onChange([...value, opt]);
    }
  }

  function addCustom() {
    const t = custom.trim();
    if (!t || value.length >= 3 || value.includes(t)) return;
    onChange([...value, t]);
    setCustom("");
  }

  return (
    <div style={{display:"flex",flexDirection:"column",gap:8,flex:1}}>

      {/* Selected angle tags */}
      {value.length > 0 && (
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {value.map((a, i) => (
            <div key={i} style={{display:"flex",alignItems:"center",gap:5,padding:"4px 6px 4px 10px",borderRadius:6,background:"var(--accent-dim)",border:"1px solid var(--accent-border)"}}>
              <span style={{fontSize:10,fontWeight:700,color:"var(--accent)",letterSpacing:"0.04em",marginRight:2}}>CUT {i+1}</span>
              <span style={{fontSize:12,color:"var(--text-primary)"}}>{a}</span>
              <button onClick={()=>onChange(value.filter((_,idx)=>idx!==i))} style={{marginLeft:2,width:16,height:16,borderRadius:3,border:"none",background:"transparent",color:"var(--text-muted)",cursor:"pointer",fontSize:12,display:"flex",alignItems:"center",justifyContent:"center",padding:0}}>×</button>
            </div>
          ))}
        </div>
      )}

      {/* Preset pills */}
      <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
        {ANGLE_PILLS.map(opt => {
          const idx = value.indexOf(opt);
          const selected = idx !== -1;
          const disabled = !selected && value.length >= 3;
          return (
            <button key={opt} onClick={()=>!disabled && toggle(opt)} style={{
              padding:"4px 10px", borderRadius:5, fontSize:12,
              cursor: disabled ? "default" : "pointer",
              background: selected ? "var(--accent-dim)" : "var(--bg-card)",
              border: `1px solid ${selected ? "var(--accent-border)" : "var(--border)"}`,
              color: selected ? "var(--accent)" : disabled ? "var(--text-muted)" : "var(--text-secondary)",
              opacity: disabled ? 0.35 : 1,
              transition: "opacity 0.1s",
            }}>
              {selected && <span style={{fontSize:10,fontWeight:700,marginRight:5}}>CUT {idx+1}</span>}
              {opt}
            </button>
          );
        })}
      </div>

      {/* Custom angle input — only shown when fewer than 3 selected */}
      {value.length < 3 && (
        <div style={{display:"flex",gap:6}}>
          <input
            value={custom}
            onChange={e=>setCustom(e.target.value)}
            onKeyDown={e=>{ if (e.key==="Enter") { e.preventDefault(); addCustom(); } }}
            placeholder={value.length===0 ? "Or type a custom angle…" : "Add another angle…"}
            style={{...inputStyle, flex:1}}
          />
          {custom.trim() && (
            <button onClick={addCustom} style={actionBtnStyle}>+ Add</button>
          )}
        </div>
      )}

      {value.length === 0 && (
        <div style={{fontSize:11,color:"var(--text-muted)"}}>
          Select up to 3 — one per cut. Leave empty to let Claude decide.
        </div>
      )}
    </div>
  );
}

// ── PillInputRow ──────────────────────────────────────────────────────────────
// A reusable row with pill quick-select + free-text input below.
// Clicking a pill populates the input; typing overrides the pill selection.

function PillInputRow({label, pills, value, onChange, placeholder}: {
  label: string;
  pills: string[];
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div style={{display:"flex",alignItems:"flex-start",gap:10}}>
      <div style={{width:130,fontSize:12,color:"var(--text-muted)",flexShrink:0,paddingTop:6}}>{label}</div>
      <div style={{display:"flex",flexDirection:"column",gap:6,flex:1}}>
        <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
          {pills.map(opt=>(
            <button key={opt} onClick={()=>onChange(opt)} style={{
              padding:"4px 10px", borderRadius:5, fontSize:12, cursor:"pointer",
              background: value===opt ? "var(--accent-dim)" : "var(--bg-card)",
              border: `1px solid ${value===opt ? "var(--accent-border)" : "var(--border)"}`,
              color: value===opt ? "var(--accent)" : "var(--text-secondary)",
            }}>{opt}</button>
          ))}
        </div>
        <input
          value={value}
          onChange={e=>onChange(e.target.value)}
          placeholder={placeholder}
          style={{...inputStyle}}
        />
      </div>
    </div>
  );
}

// ── ClipPlanEditor ────────────────────────────────────────────────────────────

function ClipPlanEditor({
  projectId, planCuts, clips, loadingClips, driveUrl,
  onAddClip, onRemoveClip, onMoveClip, onUpdateTrim, onTransitionChange,
}: {
  projectId: string;
  planCuts: PlanCut[];
  clips: ClipInfo[];
  loadingClips: boolean;
  driveUrl?: string;
  onAddClip: (cutId: string, filename: string) => void;
  onRemoveClip: (cutId: string, filename: string) => void;
  onMoveClip: (cutId: string, from: number, to: number) => void;
  onUpdateTrim: (cutId: string, filename: string, field: "start"|"end", value: number) => void;
  onTransitionChange: (cutId: string, transition: string) => void;
}) {
  const [activeCut,    setActiveCut]    = useState<string|null>(null);
  const [openTrimKey,  setOpenTrimKey]  = useState<string|null>(null); // "cutId:filename"

  // Auto-expand first cut
  useEffect(() => {
    if (planCuts.length>0 && !activeCut) setActiveCut(planCuts[0].id);
  }, [planCuts, activeCut]);

  const currentCut = planCuts.find(c=>c.id===activeCut);

  return (
    <div style={{display:"flex",flexDirection:"column",gap:0,border:"1px solid var(--border)",borderRadius:10,overflow:"hidden"}}>

      {/* Cut tabs */}
      <div style={{display:"flex",borderBottom:"1px solid var(--border)",background:"var(--bg-surface)"}}>
        {planCuts.map(cut=>(
          <button key={cut.id} onClick={()=>setActiveCut(cut.id)} style={{
            flex:1, padding:"10px 8px", border:"none", cursor:"pointer", fontSize:12,
            fontWeight: activeCut===cut.id ? 600 : 400,
            background: activeCut===cut.id ? "var(--bg-card)" : "transparent",
            color: activeCut===cut.id ? "var(--text-primary)" : "var(--text-secondary)",
            borderBottom: activeCut===cut.id ? "2px solid var(--accent)" : "2px solid transparent",
            transition:"background 0.15s",
          }}>
            <div>{cut.label.split("—")[0].trim()}</div>
            <div style={{fontSize:10,color:"var(--text-muted)",marginTop:1,fontWeight:400}}>{cut.clips.length} clip{cut.clips.length!==1?"s":""}</div>
          </button>
        ))}
      </div>

      {currentCut && (
        <div style={{display:"grid",gridTemplateColumns:"1fr 280px",minHeight:280}}>

          {/* Left: assigned clips */}
          <div style={{padding:16,borderRight:"1px solid var(--border)"}}>
            <div style={{display:"flex",alignItems:"center",justifyContent:"space-between",marginBottom:10}}>
              <div style={{fontSize:12,fontWeight:600,color:"var(--text-secondary)"}}>Sequence</div>
              <div style={{display:"flex",alignItems:"center",gap:6}}>
                <span style={{fontSize:11,color:"var(--text-muted)"}}>Transition:</span>
                {["cut","fade"].map(t=>(
                  <button key={t} onClick={()=>onTransitionChange(currentCut.id,t)} style={{padding:"3px 8px",borderRadius:4,fontSize:11,cursor:"pointer",background:currentCut.transition===t?"var(--accent-dim)":"var(--bg-hover)",border:`1px solid ${currentCut.transition===t?"var(--accent-border)":"var(--border)"}`,color:currentCut.transition===t?"var(--accent)":"var(--text-secondary)"}}>{t}</button>
                ))}
              </div>
            </div>

            {currentCut.clips.length===0 ? (
              <div style={{padding:"24px 0",textAlign:"center",color:"var(--text-muted)",fontSize:12}}>
                No clips yet — click a clip from the library →
              </div>
            ) : (
              <div style={{display:"flex",flexDirection:"column",gap:6}}>
                {currentCut.clips.map((filename, idx)=>{
                  const clipInfo = clips.find(c=>c.filename===filename);
                  const trim = currentCut.trim[filename] || {start:0, end: clipInfo?.duration||5};
                  const trimKey = `${currentCut.id}:${filename}`;
                  const trimOpen = openTrimKey===trimKey;

                  return (
                    <div key={`${filename}-${idx}`}>
                      <div style={{display:"flex",alignItems:"center",gap:8,padding:"6px 8px",background:"var(--bg-hover)",borderRadius:7,border:"1px solid var(--border)"}}>
                        {/* Thumbnail */}
                        <ClipThumb url={`${API}/api/projects/${projectId}/thumbnails/${filename.replace(/\.[^.]+$/,".jpg")}`} size={40}/>
                        {/* Info */}
                        <div style={{flex:1,minWidth:0}}>
                          <div style={{fontSize:12,fontWeight:500,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{filename}</div>
                          <div style={{fontSize:11,color:"var(--text-muted)"}}>{trim.start}s – {trim.end}s <span style={{marginLeft:4,color:"var(--accent)"}}>{(trim.end-trim.start).toFixed(1)}s</span></div>
                        </div>
                        {/* Controls */}
                        <div style={{display:"flex",gap:2}}>
                          <IconBtn title="Edit trim" onClick={()=>setOpenTrimKey(trimOpen?null:trimKey)}>✂</IconBtn>
                          <IconBtn title="Move up"   onClick={()=>onMoveClip(currentCut.id,idx,idx-1)} disabled={idx===0}>↑</IconBtn>
                          <IconBtn title="Move down" onClick={()=>onMoveClip(currentCut.id,idx,idx+1)} disabled={idx===currentCut.clips.length-1}>↓</IconBtn>
                          <IconBtn title="Remove"    onClick={()=>onRemoveClip(currentCut.id,filename)} danger>×</IconBtn>
                        </div>
                      </div>

                      {/* Inline trim editor */}
                      {trimOpen && (
                        <div style={{margin:"2px 0 4px 48px",padding:"8px 10px",background:"var(--bg-card)",border:"1px solid var(--border)",borderRadius:6,display:"flex",gap:16,alignItems:"center"}}>
                          {(["start","end"] as const).map(field=>(
                            <label key={field} style={{display:"flex",alignItems:"center",gap:6,fontSize:12,color:"var(--text-secondary)"}}>
                              {field==="start"?"In":"Out"}
                              <input
                                type="number" min={0} max={clipInfo?.duration||999} step={0.1}
                                value={trim[field]}
                                onChange={e=>onUpdateTrim(currentCut.id,filename,field,parseFloat(e.target.value)||0)}
                                style={{width:60,padding:"3px 6px",background:"var(--bg-base)",border:"1px solid var(--border)",borderRadius:4,color:"var(--text-primary)",fontSize:12}}
                              />
                              <span style={{color:"var(--text-muted)"}}>s</span>
                            </label>
                          ))}
                          {clipInfo && <span style={{fontSize:11,color:"var(--text-muted)"}}>clip: {clipInfo.duration}s</span>}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right: clip library */}
          <div style={{padding:12,overflowY:"auto",maxHeight:420}}>
            <div style={{fontSize:12,fontWeight:600,color:"var(--text-secondary)",marginBottom:8}}>
              Library {loadingClips && <span style={{fontWeight:400,color:"var(--text-muted)"}}>(loading…)</span>}
            </div>
            {!loadingClips && clips.length===0 && (
              <div style={{fontSize:12,color:"var(--text-muted)",lineHeight:1.8}}>
                No clips found.<br/>
                {driveUrl
                  ? <span>Click <strong style={{color:"var(--text-secondary)"}}>⬇ Sync Drive</strong> above to download footage.</span>
                  : <span>Add footage to <code style={{fontSize:11}}>projects/{projectId}/clips/</code>.</span>
                }
              </div>
            )}
            <div style={{display:"flex",flexDirection:"column",gap:4}}>
              {clips.map(clip=>{
                const inCut = currentCut.clips.includes(clip.filename);
                return (
                  <div
                    key={clip.filename}
                    onClick={()=>!inCut && onAddClip(currentCut.id, clip.filename)}
                    style={{
                      display:"flex",alignItems:"center",gap:8,padding:"5px 6px",
                      borderRadius:6,cursor:inCut?"default":"pointer",
                      background:inCut?"var(--bg-surface)":"var(--bg-hover)",
                      border:`1px solid ${inCut?"var(--border)":"var(--border)"}`,
                      opacity:inCut?0.45:1,
                      transition:"opacity 0.15s",
                    }}
                  >
                    <ClipThumb url={`${API}/api/projects/${projectId}/thumbnails/${clip.filename.replace(/\.[^.]+$/,".jpg")}`} size={36}/>
                    <div style={{flex:1,minWidth:0}}>
                      <div style={{fontSize:11,fontWeight:500,overflow:"hidden",textOverflow:"ellipsis",whiteSpace:"nowrap"}}>{clip.filename}</div>
                      <div style={{fontSize:10,color:"var(--text-muted)"}}>{clip.duration}s · {clip.size_mb}MB</div>
                    </div>
                    {inCut
                      ? <span style={{fontSize:10,color:"var(--text-muted)"}}>✓</span>
                      : <span style={{fontSize:13,color:"var(--accent)"}}>+</span>
                    }
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Shared sub-components ─────────────────────────────────────────────────────

function ClipThumb({url, size}: {url:string; size:number}) {
  const [err, setErr] = useState(false);
  return err ? (
    <div style={{width:size,height:size,borderRadius:4,background:"var(--bg-card)",border:"1px solid var(--border)",flexShrink:0,display:"flex",alignItems:"center",justifyContent:"center",fontSize:10,color:"var(--text-muted)"}}>?</div>
  ) : (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={url} alt="" onError={()=>setErr(true)} style={{width:size,height:size,objectFit:"cover",borderRadius:4,flexShrink:0,background:"var(--bg-card)"}}/>
  );
}

function IconBtn({children, onClick, title, disabled, danger}: {children:React.ReactNode; onClick:()=>void; title?:string; disabled?:boolean; danger?:boolean}) {
  return (
    <button title={title} onClick={onClick} disabled={disabled} style={{width:24,height:24,borderRadius:4,border:"1px solid var(--border)",background:"transparent",cursor:disabled?"not-allowed":"pointer",color:danger?"var(--red)":disabled?"var(--text-muted)":"var(--text-secondary)",fontSize:13,display:"flex",alignItems:"center",justifyContent:"center",opacity:disabled?0.35:1}}>
      {children}
    </button>
  );
}

function EmptyState({onNew}:{onNew:()=>void}) {
  return (
    <div style={{display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",height:"100%",gap:16,color:"var(--text-muted)"}}>
      <div style={{fontSize:36}}>🎬</div>
      <div style={{fontSize:15,color:"var(--text-secondary)",fontWeight:500}}>No project selected</div>
      <button onClick={onNew} style={{padding:"8px 20px",borderRadius:8,border:"none",background:"var(--accent)",color:"#0d0d0d",fontWeight:600,fontSize:13,cursor:"pointer"}}>Create your first project</button>
    </div>
  );
}

function NewProjectModal({onClose, onCreate}:{
  onClose:()=>void;
  onCreate:(name:string, brief:string, angle:string, driveUrl:string)=>Promise<void>
}) {
  const [name,     setName]     = useState("");
  const [brief,    setBrief]    = useState("");
  const [angle,    setAngle]    = useState("");
  const [driveUrl, setDriveUrl] = useState("");
  const [creating, setCreating] = useState(false);

  async function submit() {
    if (!name.trim()) return;
    setCreating(true); await onCreate(name.trim(), brief.trim(), angle.trim(), driveUrl.trim()); setCreating(false);
  }

  return (
    <div style={{position:"fixed",inset:0,background:"rgba(0,0,0,0.7)",display:"flex",alignItems:"center",justifyContent:"center",zIndex:50}} onClick={onClose}>
      <div style={{background:"var(--bg-card)",border:"1px solid var(--border)",borderRadius:12,padding:28,width:500,maxHeight:"90vh",overflowY:"auto",boxShadow:"0 24px 48px rgba(0,0,0,0.5)"}} onClick={e=>e.stopPropagation()}>
        <div style={{fontSize:16,fontWeight:600,marginBottom:20}}>New project</div>

        <Field label="Project name" hint="e.g. Turmbar Hamburg">
          <input value={name} onChange={e=>setName(e.target.value)} placeholder="My awesome venue" style={inputStyle} autoFocus/>
        </Field>

        <Field label="About the venue" hint="Describe the venue/creator, audience, and tone — Claude uses this as context for all scripts">
          <textarea rows={3} value={brief} onChange={e=>setBrief(e.target.value)} placeholder="A cocktail class venue in Hamburg targeting young professionals. Warm, self-deprecating tone." style={textareaStyle}/>
        </Field>

        <Field label="Content angle" hint="What should the video be about? Pick a preset or write your own (you can change this later)">
          <div style={{display:"flex",flexDirection:"column",gap:6}}>
            <div style={{display:"flex",gap:6,flexWrap:"wrap"}}>
              {ANGLE_PILLS.map(opt=>(
                <button key={opt} onClick={()=>setAngle(opt)} style={{
                  padding:"4px 10px", borderRadius:5, fontSize:12, cursor:"pointer",
                  background: angle===opt ? "var(--accent-dim)" : "var(--bg-card)",
                  border: `1px solid ${angle===opt ? "var(--accent-border)" : "var(--border)"}`,
                  color: angle===opt ? "var(--accent)" : "var(--text-secondary)",
                }}>{opt}</button>
              ))}
            </div>
            <input value={angle} onChange={e=>setAngle(e.target.value)} placeholder="e.g. 'Hidden gem in Hamburg'" style={inputStyle}/>
          </div>
        </Field>

        <Field label="Google Drive folder URL" hint="Optional — leave empty to use local clips">
          <input value={driveUrl} onChange={e=>setDriveUrl(e.target.value)} placeholder="https://drive.google.com/drive/folders/…" style={inputStyle}/>
        </Field>

        <div style={{display:"flex",gap:8,justifyContent:"flex-end",marginTop:8}}>
          <button onClick={onClose} style={{padding:"8px 16px",borderRadius:7,border:"1px solid var(--border)",background:"transparent",color:"var(--text-secondary)",cursor:"pointer",fontSize:13}}>Cancel</button>
          <button onClick={submit} disabled={creating||!name.trim()} style={{padding:"8px 20px",borderRadius:7,border:"none",background:"var(--accent)",color:"#0d0d0d",fontWeight:600,fontSize:13,cursor:"pointer"}}>{creating?"Creating…":"Create project"}</button>
        </div>
      </div>
    </div>
  );
}

function Field({label,hint,children}:{label:string;hint?:string;children:React.ReactNode}) {
  return (
    <div style={{marginBottom:16}}>
      <div style={{fontSize:12,fontWeight:600,marginBottom:4}}>{label}</div>
      {hint && <div style={{fontSize:11,color:"var(--text-muted)",marginBottom:6}}>{hint}</div>}
      {children}
    </div>
  );
}

function Section({title,subtitle,children,action}:{title:string;subtitle:string;children:React.ReactNode;action?:React.ReactNode}) {
  return (
    <div style={{marginBottom:28}}>
      <div style={{display:"flex",alignItems:"baseline",justifyContent:"space-between",marginBottom:10}}>
        <div>
          <div style={{fontSize:13,fontWeight:600,marginBottom:2}}>{title}</div>
          {subtitle && <div style={{fontSize:12,color:"var(--text-muted)"}}>{subtitle}</div>}
        </div>
        {action}
      </div>
      {children}
    </div>
  );
}

function Spinner({size=14}:{size?:number}) {
  return <span style={{display:"inline-block",width:size,height:size,border:"2px solid #555",borderTopColor:"var(--accent)",borderRadius:"50%",animation:"spin 0.7s linear infinite"}}/>;
}

function Checkbox({checked}:{checked:boolean}) {
  return <span style={{width:14,height:14,borderRadius:3,flexShrink:0,border:`1.5px solid ${checked?"var(--accent)":"var(--text-muted)"}`,background:checked?"var(--accent)":"transparent",display:"inline-flex",alignItems:"center",justifyContent:"center",fontSize:9,color:"#0d0d0d"}}>{checked?"✓":""}</span>;
}

// ── Styles ────────────────────────────────────────────────────────────────────

const inputStyle: React.CSSProperties = {width:"100%",padding:"8px 11px",background:"var(--bg-base)",border:"1px solid var(--border)",borderRadius:6,color:"var(--text-primary)",fontSize:13,outline:"none",boxSizing:"border-box"};
const textareaStyle: React.CSSProperties = {width:"100%",padding:"9px 11px",background:"var(--bg-base)",border:"1px solid var(--border)",borderRadius:6,color:"var(--text-primary)",fontSize:13,resize:"vertical",outline:"none",lineHeight:1.6,boxSizing:"border-box"};
const cardStyle: React.CSSProperties = {padding:16,background:"var(--bg-card)",border:"1px solid var(--border)",borderRadius:10};
const chipStyle: React.CSSProperties = {display:"flex",alignItems:"center",gap:6,padding:"7px 11px",borderRadius:7,cursor:"pointer",fontSize:12};
const actionBtnStyle: React.CSSProperties = {padding:"5px 12px",borderRadius:6,border:"1px solid var(--accent-border)",background:"var(--accent-dim)",color:"var(--accent)",fontSize:12,fontWeight:500,cursor:"pointer"};
