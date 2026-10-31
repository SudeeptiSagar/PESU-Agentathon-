import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import CrystalizedBall from "./src/components/CrystalizedBall.jsx";
import "./console.css";

const REDACTED_INPUT = "Sensitive entry sent";
const BROWSER_TTS_ENABLED =
  String(import.meta.env.VITE_TTS_BACKEND || "browser").toLowerCase() === "browser";
const COLORS = {
  ready: { preset: "frost", color: "#9bbcff" },
  listening: { preset: "aurora", color: "#65f4d8" },
  thinking: { preset: "nebula", color: "#9a83ff" },
  answering: { preset: "ember", color: "#ff9c76" },
  awaiting: { preset: "solar", color: "#ffd36e" },
  paused: { preset: "frost", color: "#b8dfff" },
  error: { preset: "ember", color: "#ff647c" },
};

function statusFor(name) {
  switch (String(name || "").toUpperCase()) {
    case "LISTENING":
      return { phase: "listening", label: "Listening" };
    case "PLANNING":
    case "ACTING":
    case "VERIFYING":
    case "COMMITTING":
      return { phase: "thinking", label: "Thinking" };
    case "READBACK":
    case "DONE":
      return { phase: "answering", label: "Answering" };
    case "AWAITING_CONFIRM":
      return { phase: "awaiting", label: "Waiting for confirmation" };
    case "NEEDS_HUMAN_CHECK":
      return { phase: "awaiting", label: "Waiting for you" };
    case "NEEDS_USER":
    case "NEEDS_USER_INPUT":
      return { phase: "awaiting", label: "Needs your answer" };
    case "PAUSED":
      return { phase: "paused", label: "Paused" };
    case "ERROR":
      return { phase: "error", label: "Needs attention" };
    default:
      return { phase: "ready", label: "Ready" };
  }
}

function useConsoleSocket(onEvent) {
  const socketRef = useRef(null);
  const eventRef = useRef(onEvent);
  const [connection, setConnection] = useState("connecting");

  useEffect(() => {
    eventRef.current = onEvent;
  }, [onEvent]);

  useEffect(() => {
    let active = true;
    let timer = 0;
    let delay = 500;

    const connect = () => {
      if (!active) return;
      const protocol = location.protocol === "https:" ? "wss:" : "ws:";
      const socket = new WebSocket(`${protocol}//${location.host}/ws/console`);
      socketRef.current = socket;
      setConnection("connecting");

      socket.onopen = () => {
        if (!active) return socket.close();
        delay = 500;
        setConnection("connected");
      };
      socket.onmessage = ({ data }) => {
        try {
          const event = JSON.parse(data);
          if (typeof event?.type === "string") eventRef.current(event);
        } catch {
          eventRef.current({
            type: "alert",
            level: "warning",
            message: "A console update could not be read.",
          });
        }
      };
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (!active) return;
        setConnection("reconnecting");
        timer = window.setTimeout(connect, delay);
        delay = Math.min(delay * 1.8, 10000);
      };
    };

    connect();
    return () => {
      active = false;
      window.clearTimeout(timer);
      socketRef.current?.close();
      socketRef.current = null;
    };
  }, []);

  const send = useCallback((payload) => {
    const socket = socketRef.current;
    if (!socket || socket.readyState !== WebSocket.OPEN) return false;
    socket.send(JSON.stringify(payload));
    return true;
  }, []);

  return { connection, send };
}

function Activity({ steps, transcript, fields, pending, alerts, connection }) {
  return (
    <section className="activity-panel" aria-label="Assistant activity">
      <div className="activity-heading">
        <span className={`connection-dot connection-dot--${connection}`} />
        <span>{connection === "connected" ? "Connected" : "Reconnecting"}</span>
      </div>

      {pending && (
        <section className="activity-block activity-pending" aria-label="Pending action">
          <h2>Waiting for confirmation</h2>
          <p>{pending.description || "An action is ready for your review."}</p>
        </section>
      )}

      {alerts.length > 0 && (
        <section className="activity-block" aria-label="Alerts">
          {alerts.slice(-3).map((alert, index) => (
            <p className={`activity-alert activity-alert--${alert.level}`} key={`${index}-${alert.message}`}>
              {alert.message}
            </p>
          ))}
        </section>
      )}

      {fields.length > 0 && (
        <section className="activity-block" aria-label="Masked page fields">
          <h2>Fields</h2>
          <div className="field-table" role="table" aria-label="Masked fields">
            {fields.slice(0, 8).map((field, index) => (
              <div className="field-row" role="row" key={`${field.label}-${index}`}>
                <span role="cell">{field.label || "Field"}</span>
                <span role="cell">{field.value_masked || "Hidden"}</span>
                <span role="cell">{field.status || ""}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {steps.length > 0 && (
        <section className="activity-block" aria-label="Live steps">
          <h2>Steps</h2>
          <ol className="step-list" aria-live="polite" aria-relevant="additions text">
            {steps.slice(-8).reverse().map((step, index) => (
              <li key={`${step.n || index}-${step.action || "step"}`}>
                <span>{step.action || "Working"}</span>
                {[step.target, step.result].filter(Boolean).join(" · ")}
              </li>
            ))}
          </ol>
        </section>
      )}

      {transcript.length > 0 && (
        <section className="activity-block" aria-label="Recent transcript">
          <h2>Transcript</h2>
          <ol className="transcript-list" aria-live="polite" aria-relevant="additions text">
            {transcript.slice(-6).reverse().map((item, index) => (
              <li key={`${index}-${item.role}-${item.text}`}>
                <span>{item.role === "assistant" ? "Agent" : "You"}</span>
                {item.text}
              </li>
            ))}
          </ol>
        </section>
      )}
    </section>
  );
}

function AssistantOrb() {
  const inputRef = useRef(null);
  const [status, setStatus] = useState({ phase: "ready", label: "Ready" });
  const [draft, setDraft] = useState("");
  const [inputMode, setInputMode] = useState("voice");
  const [activityOpen, setActivityOpen] = useState(false);
  const [steps, setSteps] = useState([]);
  const [transcript, setTranscript] = useState([]);
  const [fields, setFields] = useState([]);
  const [pending, setPending] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [announcement, setAnnouncement] = useState("Ready");

  const handleEvent = useCallback((event) => {
    switch (event.type) {
      case "state": {
        const next = statusFor(event.name);
        setStatus(next);
        setAnnouncement(next.label);
        if (["IDLE", "DONE"].includes(String(event.name).toUpperCase()))
          setPending(null);
        if (["AWAITING_CONFIRM", "NEEDS_HUMAN_CHECK", "NEEDS_USER"].includes(String(event.name).toUpperCase()))
          setActivityOpen(true);
        break;
      }
      case "speak":
        if (event.text) {
          setStatus({ phase: "answering", label: "Answering" });
          if (
            BROWSER_TTS_ENABLED &&
            "speechSynthesis" in window &&
            typeof SpeechSynthesisUtterance === "function"
          ) {
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(new SpeechSynthesisUtterance(event.text));
            setAnnouncement("Answering");
          } else {
            setAnnouncement(event.text);
          }
          setTranscript((current) => [...current, { role: "assistant", text: event.text }].slice(-12));
        }
        break;
      case "step":
        setSteps((current) => [...current, event].slice(-24));
        setStatus({ phase: "thinking", label: "Thinking" });
        setAnnouncement([event.action, event.target, event.result].filter(Boolean).join(". ") || "Working");
        break;
      case "field_table":
        setFields(Array.isArray(event.fields) ? event.fields : []);
        break;
      case "pending":
        setPending({ description: event.description || "Review the requested action." });
        setStatus({ phase: "awaiting", label: "Waiting for confirmation" });
        setAnnouncement(event.description || "An action is waiting for your confirmation.");
        setActivityOpen(true);
        break;
      case "alert":
        if (event.message) {
          const alert = { level: event.level || "info", message: event.message };
          setAlerts((current) => [...current, alert].slice(-8));
          setAnnouncement(event.message);
          if (event.level === "error") setStatus({ phase: "error", label: "Needs attention" });
          setActivityOpen(true);
        }
        break;
      case "input_mode":
        setDraft("");
        setInputMode(event.mode === "typed_secret" ? "typed_secret" : "voice");
        if (event.mode === "voice") {
          setStatus({ phase: "listening", label: "Listening" });
          setAnnouncement("Listening");
        }
        break;
      default:
        break;
    }
  }, []);

  const { connection, send } = useConsoleSocket(handleEvent);

  const sendDraft = useCallback(() => {
    const text = draft.trim();
    if (!text) return;
    if (!send({ type: "utterance", text })) {
      setAnnouncement("Reconnecting. Your request is still here.");
      return;
    }
    const secret = inputMode === "typed_secret";
    setTranscript((current) => [...current, { role: "user", text: secret ? REDACTED_INPUT : text }].slice(-12));
    setAnnouncement(secret ? REDACTED_INPUT : "Request sent");
    setStatus({ phase: "thinking", label: "Thinking" });
    setDraft("");
  }, [draft, inputMode, send]);

  useEffect(() => {
    if (!draft.trim() || connection !== "connected") return undefined;
    const timer = window.setTimeout(sendDraft, 900);
    return () => window.clearTimeout(timer);
  }, [draft, connection, sendDraft]);

  const sendKey = useCallback((name) => {
    if (name === "Escape") window.speechSynthesis?.cancel();
    if (!send({ type: "key", name })) {
      setAnnouncement("Console reconnecting. The command was not sent.");
      return;
    }
    if (name === "Escape") setAnnouncement("Stop requested");
    if (name === "Space") setAnnouncement("Pause or continue requested");
  }, [send]);

  useEffect(() => {
    inputRef.current?.focus({ preventScroll: true });
  }, [inputMode]);

  const handleKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      sendKey("Escape");
    } else if (event.code === "Space" && !draft.trim()) {
      event.preventDefault();
      sendKey("Space");
    } else if (event.altKey && event.key.toLowerCase() === "i") {
      event.preventDefault();
      setActivityOpen((open) => !open);
    } else if (event.key === "Enter") {
      event.preventDefault();
      sendDraft();
    }
  };

  const phase = connection === "connected" ? status.phase : "error";
  const orb = COLORS[phase] || COLORS.ready;
  const connectionLabel =
    connection === "connected"
      ? "connected"
      : connection === "connecting"
        ? "connecting"
        : "reconnecting";

  return (
    <main className={`orb-screen orb-screen--${phase}`}>
      <button
        type="button"
        className="orb-button"
        aria-label={`PESU assistant. ${status.label}. Console ${connectionLabel}. Click to ${activityOpen ? "hide" : "view"} activity.`}
        aria-expanded={activityOpen}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => setActivityOpen((open) => !open)}
      >
        <span className="orb-aura" aria-hidden="true" />
        <CrystalizedBall
          className="assistant-ball"
          preset={orb.preset}
          color={orb.color}
          size={0.78}
          particleCount={16000}
          speed={phase === "thinking" ? 1.15 : 0.72}
          interactive={false}
          intro={false}
          paused={phase === "paused"}
        />
      </button>

      <input
        ref={inputRef}
        className="capture-input"
        type={inputMode === "typed_secret" ? "password" : "text"}
        value={draft}
        autoComplete="off"
        spellCheck={false}
        aria-label={inputMode === "typed_secret" ? "Sensitive entry" : "Task input"}
        aria-describedby="input-help"
        onChange={(event) => {
          if (BROWSER_TTS_ENABLED) window.speechSynthesis?.cancel();
          setDraft(event.target.value);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => window.setTimeout(() => inputRef.current?.focus({ preventScroll: true }), 0)}
      />
      <span id="input-help" className="visually-hidden">
        Handy pastes the request here. Enter sends it. Escape stops the agent. Alt plus I opens activity.
        {inputMode === "typed_secret" ? " Typed characters are hidden." : ""}
      </span>

      {activityOpen && (
        <Activity
          steps={steps}
          transcript={transcript}
          fields={fields}
          pending={pending}
          alerts={alerts}
          connection={connection}
        />
      )}

      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      <div className="visually-hidden" role="alert" aria-live="assertive">
        {alerts.at(-1)?.message || ""}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AssistantOrb />
  </React.StrictMode>,
);
