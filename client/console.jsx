import React, { useCallback, useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import CrystalizedBall from "./src/components/CrystalizedBall.jsx";
import "./console.css";

// Polyfill Array.prototype.at for older Chromium / QtWebEngine compatibility
if (!Array.prototype.at) {
  Array.prototype.at = function (n) {
    n = Math.trunc(n) || 0;
    if (n < 0) n += this.length;
    if (n < 0 || n >= this.length) return undefined;
    return this[n];
  };
}

const isOverlay =
  typeof window !== "undefined" &&
  (new URLSearchParams(window.location.search).get("overlay") === "1" ||
    window.location.search.includes("overlay"));


const REDACTED_INPUT = "Sensitive entry sent";
const BROWSER_TTS_ENABLED =
  String(import.meta.env.VITE_TTS_BACKEND || "browser").toLowerCase() === "browser";
const COLORS = {
  ready: { preset: "frost", color: "#9bbcff" },
  listening: { preset: "aurora", color: "#65f4d8" },
  thinking: { preset: "nebula", color: "#9a83ff" },
  acting: { preset: "aurora", color: "#38bdf8" },
  answering: { preset: "ember", color: "#ff9c76" },
  awaiting: { preset: "solar", color: "#ffd36e" },
  paused: { preset: "frost", color: "#b8dfff" },
  stopped: { preset: "frost", color: "#94a3b8" },
  error: { preset: "ember", color: "#ff647c" },
};

function statusFor(name) {
  switch (String(name || "").toUpperCase()) {
    case "LISTENING":
      return { phase: "listening", label: "Listening" };
    case "PLANNING":
    case "VERIFYING":
    case "COMMITTING":
      return { phase: "thinking", label: "Thinking" };
    case "ACTING":
      return { phase: "acting", label: "Acting in browser" };
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
    case "STOPPED":
      return { phase: "stopped", label: "Stopped" };
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
    <section
      id="activity-panel"
      className="activity-panel"
      aria-label="Assistant activity"
      tabIndex={0}
    >
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
          <table className="field-table" aria-label="Masked fields">
            <thead>
              <tr>
                <th scope="col">Field</th>
                <th scope="col">Masked value</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              {fields.slice(0, 8).map((field, index) => (
                <tr key={`${field.label}-${index}`}>
                  <th scope="row">{field.label || "Field"}</th>
                  <td>{field.value_masked || "Hidden"}</td>
                  <td>{field.status || "Unknown"}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
          <ol className="transcript-list">
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
  const messageSequenceRef = useRef(0);
  const [status, setStatus] = useState({ phase: "ready", label: "Ready" });
  const [draft, setDraft] = useState("");
  const [inputMode, setInputMode] = useState("voice");
  const [inputExpanded, setInputExpanded] = useState(false);
  const [inputFocused, setInputFocused] = useState(false);
  const [activityOpen, setActivityOpen] = useState(false);
  const [steps, setSteps] = useState([]);
  const [transcript, setTranscript] = useState([]);
  const [agentMessages, setAgentMessages] = useState([]);
  const [fields, setFields] = useState([]);
  const [pending, setPending] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [announcement, setAnnouncement] = useState("Ready");
  useEffect(() => {
    if (isOverlay) {
      document.documentElement.classList.add("overlay-mode");
      document.body.classList.add("overlay-mode");
    }
  }, []);

  const suppressInitialFocusReveal = useRef(true);
  const browserTtsAvailable =
    BROWSER_TTS_ENABLED &&
    "speechSynthesis" in window &&
    typeof SpeechSynthesisUtterance === "function";

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
          const messageId = messageSequenceRef.current++;
          setStatus({ phase: "answering", label: "Answering" });
          if (browserTtsAvailable) {
            window.speechSynthesis.cancel();
            window.speechSynthesis.speak(new SpeechSynthesisUtterance(event.text));
          }
          setAnnouncement("Answering");
          setAgentMessages((current) => [...current, { id: messageId, text: event.text }].slice(-6));
          setTranscript((current) => [...current, { role: "assistant", text: event.text }].slice(-12));
        }
        break;
      case "step":
        setSteps((current) => [...current, event].slice(-24));
        setStatus({ phase: "acting", label: "Acting in browser" });
        setAnnouncement("Working");
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
          setAnnouncement(event.level === "error" ? "Error" : "Alert");
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
  }, [browserTtsAvailable]);

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
    setInputExpanded(false);
    setInputFocused(false);
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
    if (name === "Escape") {

      setStatus({ phase: "stopped", label: "Stopped" });

      setAnnouncement("Stop requested");

    }
    if (name === "Space") setAnnouncement("Pause or continue requested");
  }, [send]);

  useEffect(() => {
    // Give Handy a paste target at startup. This first programmatic focus stays
    // visually quiet; typing or a keyboard focus action reveals the field.
    inputRef.current?.focus({ preventScroll: true });
    suppressInitialFocusReveal.current = false;
  }, []);

  const handleKeyDown = (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      sendDraft();
    }
  };

  const handleMainKeyDown = (event) => {
    if (event.key === "Escape") {
      event.preventDefault();
      sendKey("Escape");
    } else if (event.altKey && event.key.toLowerCase() === "i") {
      event.preventDefault();
      setActivityOpen((open) => !open);
    } else if (event.altKey && event.key.toLowerCase() === "t") {
      event.preventDefault();
      setInputExpanded(true);
      inputRef.current?.focus({ preventScroll: true });
    } else if (
      event.code === "Space" &&
      event.target === inputRef.current &&
      !draft.trim()
    ) {
      event.preventDefault();
      sendKey("Space");
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
    <main className={`orb-screen orb-screen--${phase}${isOverlay ? " orb-screen--overlay" : ""}`}
      onClick={() => inputRef.current?.focus({ preventScroll: true })} onKeyDown={handleMainKeyDown}>
      <input
        ref={inputRef}
        className={`capture-input${draft || inputExpanded || inputFocused ? " capture-input--visible" : ""}`}
        type={inputMode === "typed_secret" ? "password" : "text"}
        value={draft}
        autoComplete="off"
        spellCheck={false}
        aria-label={inputMode === "typed_secret" ? "Sensitive entry" : "Task input"}
        aria-describedby="input-help"
        onFocus={() => {
          if (!suppressInitialFocusReveal.current) setInputFocused(true);
        }}
        onBlur={() => setInputFocused(false)}
        onChange={(event) => {
          if (BROWSER_TTS_ENABLED) window.speechSynthesis?.cancel();
          setDraft(event.target.value);
        }}
        onKeyDown={handleKeyDown}
      />
      <span id="input-help" className="visually-hidden">
        Handy pastes the request here. Enter sends it. Escape stops the agent. Alt plus I opens activity.
        Alt plus T shows the task input. {inputMode === "typed_secret" ? " Typed characters are hidden." : ""}
      </span>
      <button
        type="button"
        className="orb-button"
        aria-label={`PESU assistant. ${status.label}. Console ${connectionLabel}. Click to ${activityOpen ? "hide" : "view"} activity.`}
        aria-expanded={activityOpen}
        aria-controls="activity-panel"
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => {
          inputRef.current?.focus({ preventScroll: true });
          if (!isOverlay) setActivityOpen((open) => !open);
        }}
      >
        <span className="orb-aura" aria-hidden="true" />
        <CrystalizedBall
          className="assistant-ball"
          preset={orb.preset}
          color={orb.color}
          size={isOverlay ? 0.72 : 0.78}
          particleCount={16000}
          speed={phase === "thinking" ? 1.15 : phase === "acting" ? 1.35 : 0.72}
          interactive={false}
          intro={false}
          paused={phase === "paused"}
        />
      </button>

      <div className="orb-subtitle" aria-hidden="true">
        {draft
          ? (inputMode === "typed_secret" ? "••••••••" : draft)
          : (pending?.description || (agentMessages.length > 0 ? agentMessages[agentMessages.length - 1].text : status.label))
        }
      </div>

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

      <ol
        className="visually-hidden"
        role="log"
        aria-label="Agent messages"
        aria-live={browserTtsAvailable ? "off" : "polite"}
        aria-relevant="additions"
        aria-atomic="false"
      >
        {agentMessages.map((message) => <li key={message.id}>{message.text}</li>)}
      </ol>
      <div className="visually-hidden" role="status" aria-live="polite" aria-atomic="true">
        {announcement}
      </div>
      <div className="visually-hidden" role="alert" aria-live="assertive" aria-atomic="true">
        {(alerts.length ? alerts[alerts.length - 1]?.message : "") || ""}
      </div>
    </main>
  );
}

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AssistantOrb />
  </React.StrictMode>,
);
