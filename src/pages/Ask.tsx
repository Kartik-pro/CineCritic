import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { api } from "../api";
import { ErrorNote } from "../components/Status";
import { useApp } from "../state";

const SUGGESTIONS = [
  "How is the cinematography used to tell the story?",
  "What are the main themes?",
  "Which similar films should I watch next?",
];

export function Ask() {
  const { current, history, prefs, chat, setChat } = useApp();
  const films = useMemo(() => {
    const all = current ? [current, ...history] : history;
    return all.filter((a, i) => all.findIndex((b) => b.movie.id === a.movie.id) === i);
  }, [current, history]);
  const [filmId, setFilmId] = useState<number | null>(current?.movie.id ?? films[0]?.movie.id ?? null);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ block: "end" });
  }, [chat, loading]);

  const analysis = films.find((a) => a.movie.id === filmId) ?? null;

  const send = async (question: string) => {
    const trimmed = question.trim();
    if (!trimmed || loading) return;
    const before = chat;
    setChat([...before, { role: "user", content: trimmed }]);
    setInput("");
    setLoading(true);
    setError("");
    try {
      const { answer } = await api.ask(trimmed, before, analysis, prefs);
      setChat((prev) => [...prev, { role: "assistant", content: answer }]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not get an answer.");
    } finally {
      setLoading(false);
    }
  };

  const submit = (event: FormEvent) => {
    event.preventDefault();
    void send(input);
  };

  return (
    <div className="chat-page">
      <h2 className="page-title">Ask the Critic</h2>
      <div className="row">
        <label>
          Film context
          <select value={filmId ?? ""} onChange={(e) => setFilmId(e.target.value ? Number(e.target.value) : null)}>
            <option value="">No specific film</option>
            {films.map((a) => (
              <option key={a.movie.id} value={a.movie.id}>
                {a.movie.title} {a.movie.year && `(${a.movie.year})`}
              </option>
            ))}
          </select>
        </label>
        {chat.length > 0 && (
          <button className="ghost" onClick={() => setChat([])}>
            Clear chat
          </button>
        )}
      </div>

      <div className="messages" aria-live="polite">
        {chat.length === 0 && (
          <div className="suggestions">
            <p className="muted">
              {films.length ? "Ask about the selected film, or film craft in general." : "Analyze a film first for grounded answers, or just ask."}
            </p>
            {SUGGESTIONS.map((s) => (
              <button key={s} className="chip" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {chat.map((m, i) => (
          <div key={i} className={`bubble ${m.role}`}>
            {m.content}
          </div>
        ))}
        {loading && <div className="bubble assistant typing">Thinking…</div>}
        <div ref={end} />
      </div>
      <ErrorNote message={error} />
      <form className="composer" onSubmit={submit}>
        <input
          type="text"
          maxLength={800}
          value={input}
          placeholder="Ask a question about film…"
          aria-label="Your question"
          onChange={(e) => setInput(e.target.value)}
        />
        <button className="primary" type="submit" disabled={loading || !input.trim()}>
          Send
        </button>
      </form>
    </div>
  );
}
