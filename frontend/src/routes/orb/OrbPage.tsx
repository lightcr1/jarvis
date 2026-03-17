import React, { useRef, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { useAuth } from "../../features/auth/AuthProvider";
import { sendChatMessage, synthesizeSpeech, transcribeAudio } from "../../shared/api/chat";

export function OrbPage() {
  const { user, preferences } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState("idle");
  const [error, setError] = useState("");
  const [lastInputMode, setLastInputMode] = useState("voice");
  const audioRef = useRef(new Audio());

  if (!user) return <Navigate to="/login" replace />;

  async function executePrompt(text: string, source: string) {
    setLastInputMode(source);
    setState("thinking");
    const replyPayload = await sendChatMessage(text, source, "orb");

    if (preferences.auto_play_voice !== false && replyPayload.reply) {
      setState("speaking");
      const blobAudio = await synthesizeSpeech(replyPayload.reply || "");
      audioRef.current.src = URL.createObjectURL(blobAudio);
      await audioRef.current.play().catch(() => undefined);
    }

    setState("idle");
  }

  async function runOrb() {
    setError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const recorder = new MediaRecorder(stream);
      const chunks: BlobPart[] = [];
      recorder.ondataavailable = (event) => chunks.push(event.data);
      recorder.onstop = async () => {
        try {
          setState("transcribing");
          const blob = new Blob(chunks, { type: "audio/webm" });
          const textPayload = await transcribeAudio(blob, "orb");
          await executePrompt(textPayload.text || "status jarvis", "voice");
        } catch (err) {
          setError((err as Error).message);
          setState("error");
        } finally {
          stream.getTracks().forEach((track) => track.stop());
        }
      };
      setState("listening");
      recorder.start();
      setTimeout(() => recorder.stop(), 2500);
    } catch (err) {
      setError((err as Error).message);
      setState("error");
    }
  }

  return (
    <div className={`orb-screen orb-${preferences.orb_detail || "medium"}`}>
      <div className="orb-topbar">
        <div>
          <div className="eyebrow">Orb Mode</div>
          <h1>Voice-first Jarvis interface</h1>
        </div>
        <div className="inline-actions">
          <button className="ui-button ghost" onClick={() => navigate("/chat")}>Back to chat</button>
          <div className="status-chip">{user.username}</div>
        </div>
      </div>
      <div className="orb-stage">
        <div className="orb-assembly orb-assembly-left">
          <span className="orb-assembly-spine" />
          <span className="orb-assembly-cap orb-assembly-cap-top" />
          <span className="orb-assembly-cap orb-assembly-cap-bottom" />
          <span className="orb-assembly-bracket orb-assembly-bracket-a" />
          <span className="orb-assembly-node orb-assembly-node-a" />
        </div>
        <div className="orb-assembly orb-assembly-right">
          <span className="orb-assembly-spine" />
          <span className="orb-assembly-cap orb-assembly-cap-top" />
          <span className="orb-assembly-cap orb-assembly-cap-bottom" />
          <span className="orb-assembly-bracket orb-assembly-bracket-a" />
          <span className="orb-assembly-node orb-assembly-node-a" />
        </div>
        <div className="orb-floor-ring">
          <span className="orb-floor-ring-inner" />
        </div>
        <div className="orb-stage-info orb-stage-info-left">
          <div className="eyebrow">Input</div>
          <strong>{lastInputMode}</strong>
          <span>{state === "idle" ? "Ready for wake or tap" : state}</span>
        </div>
        <div className="orb-stage-info orb-stage-info-right">
          <div className="eyebrow">Voice</div>
          <strong>{preferences.auto_play_voice === false ? "Manual" : "Auto"}</strong>
          <span>{preferences.display_name || user.username}</span>
        </div>
        <div className="orb-constellation">
          <span className="orb-trace orb-trace-a" />
          <span className="orb-fragment orb-fragment-a" />
          <span className="orb-particle orb-particle-a" />
        </div>
        <div className="orb-ring-layer">
          <span className="orb-ring orb-ring-a" />
          <span className="orb-ring orb-ring-b" />
          <span className="orb-ring orb-ring-c" />
        </div>
        <div className="orb-halo" />
        <button className={`orb-core ${state}`} onClick={() => runOrb()} />
        <div className="orb-state">{state}</div>
        <div className="orb-quick-actions">
          <button className="toolbar-chip" onClick={() => executePrompt("status jarvis", "quick_action")}>Status prompt</button>
          <button className="toolbar-chip" onClick={() => executePrompt("summarize audit activity", "quick_action")}>Audit prompt</button>
        </div>
      </div>
      {error ? <div className="error-text orb-error">{error}</div> : null}
    </div>
  );
}
