import { FormEvent, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Menu, Send } from "lucide-react";
import { deleteSession, getSession, getStats, listSessions, sendMessage } from "./api";
import { CitationList, Comparison, ProjectCards, PropertyCards } from "./components/Cards";
import { Sidebar } from "./components/Sidebar";
import type { ChatMessage, SessionSummary } from "./types";

const PROMPTS = [
  "Explore DarGlobal developments.",
  "Find apartments in Riyadh.",
  "Show properties under SAR 1 million.",
  "Compare DarGlobal and Wasalt.",
  "What are the latest DarGlobal announcements?",
];

export default function App() {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sourceFilter, setSourceFilter] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [records, setRecords] = useState<number | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  async function refreshSessions() {
    const data = await listSessions();
    setSessions(data.sessions);
  }

  useEffect(() => {
    refreshSessions().catch(() => setError("The EstateIQ API is not reachable."));
    getStats()
      .then((stats) => setRecords(stats.records))
      .catch(() => setRecords(null));
  }, []);

  useEffect(() => {
    const transcript = transcriptRef.current;
    if (!transcript) return;
    transcript.scrollTo({ top: transcript.scrollHeight, behavior: "smooth" });
  }, [messages, loading]);

  function startNew() {
    setSessionId(null);
    setMessages([]);
    setError(null);
    setMenuOpen(false);
  }

  async function openSession(id: string) {
    setMenuOpen(false);
    setError(null);
    const data = await getSession(id);
    setSessionId(id);
    setMessages(
      data.messages.map((message) => ({
        id: message.id,
        role: message.role,
        content: message.content,
        payload: message.payload,
      })),
    );
  }

  async function clearActive() {
    if (sessionId) {
      await deleteSession(sessionId);
      await refreshSessions();
    }
    startNew();
  }

  async function submit(text: string) {
    const message = text.trim();
    if (!message || loading) return;
    setDraft("");
    setError(null);
    setMessages((current) => [...current, { id: `local-${Date.now()}`, role: "user", content: message }]);
    setLoading(true);
    try {
      const response = await sendMessage(message, sessionId, sourceFilter);
      setSessionId(response.session_id);
      setMessages((current) => [
        ...current,
        { id: `assistant-${Date.now()}`, role: "assistant", content: response.answer, payload: response },
      ]);
      await refreshSessions();
    } catch (err) {
      setError(err instanceof Error ? err.message : "The request failed.");
    } finally {
      setLoading(false);
    }
  }

  function onSubmit(event: FormEvent) {
    event.preventDefault();
    void submit(draft);
  }

  return (
    <div className="flex h-full overflow-hidden bg-sand text-ink">
      <Sidebar
        open={menuOpen}
        sessions={sessions}
        activeId={sessionId}
        sourceFilter={sourceFilter}
        onClose={() => setMenuOpen(false)}
        onNew={startNew}
        onSelect={(id) => void openSession(id)}
        onFilter={setSourceFilter}
        onClear={() => void clearActive()}
      />
      <main className="flex h-full min-w-0 flex-1 flex-col">
        <header className="flex shrink-0 items-center justify-between px-4 py-4 lg:px-10">
          <button className="rounded-full bg-ink p-2 text-sand lg:hidden" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu size={18} />
          </button>
          <p className="text-xs uppercase tracking-[0.22em] text-mist">
            {records == null ? "Public DarGlobal and Wasalt index" : `${records} indexed records`}
          </p>
          <span className="hidden text-xs uppercase tracking-[0.18em] text-gold sm:inline">
            {sourceFilter === "darglobal" ? "DarGlobal" : sourceFilter === "wasalt" ? "Wasalt" : "Both sources"}
          </span>
        </header>
        <section className="mx-auto flex min-h-0 w-full max-w-4xl flex-1 flex-col px-4 lg:px-8">
          <div ref={transcriptRef} className="no-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain pb-4">
          {messages.length === 0 && (
            <div className="py-8 sm:py-16">
              <p className="text-xs uppercase tracking-[0.28em] text-gold">EstateIQ</p>
              <h2 className="mt-3 max-w-2xl font-serif text-5xl leading-[1.05] text-ink sm:text-6xl">
                Intelligence for two real estate sources.
              </h2>
              <p className="mt-5 max-w-xl text-lg leading-8 text-navy/80">
                Ask about DarGlobal developments or Wasalt listings. Answers stay tied to the pages EstateIQ has indexed,
                with the original source attached.
              </p>
              <div className="mt-8 grid gap-3 sm:grid-cols-2">
                {PROMPTS.map((prompt, index) => (
                  <button
                    key={prompt}
                    onClick={() => void submit(prompt)}
                    className="rounded-2xl border border-line bg-paper px-4 py-4 text-left shadow-card transition hover:-translate-y-0.5"
                  >
                    <span className="text-xs text-gold">0{index + 1}</span>
                    <span className="mt-2 block text-sm text-ink">{prompt}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
          <div className="flex flex-col gap-6">
            {messages.map((message) => (
              <article key={message.id} className={message.role === "user" ? "ml-auto max-w-2xl" : "max-w-3xl"}>
                <p className="mb-1 text-xs uppercase tracking-[0.16em] text-mist">
                  {message.role === "user" ? "You" : "EstateIQ"}
                </p>
                <div
                  className={
                    message.role === "user"
                      ? "rounded-3xl rounded-br-md bg-ink px-5 py-4 text-sand"
                      : "rounded-3xl border border-line bg-paper px-5 py-4 shadow-card"
                  }
                >
                  {message.role === "assistant" ? (
                    <div className="markdown leading-7">
                      <ReactMarkdown>{message.content}</ReactMarkdown>
                    </div>
                  ) : (
                    <p className="leading-7">{message.content}</p>
                  )}
                  {message.payload && (
                    <>
                      <PropertyCards items={message.payload.properties} />
                      <ProjectCards items={message.payload.projects} />
                      <Comparison table={message.payload.comparison} />
                      <CitationList items={message.payload.citations} />
                      {!message.payload.llm_used && message.payload.grounded && (
                        <p className="mt-3 text-xs text-mist">Narrative generation was unavailable. The cards are from the index.</p>
                      )}
                    </>
                  )}
                </div>
              </article>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-mist">
                <span className="h-2 w-2 animate-pulse rounded-full bg-gold" />
                Searching the index
              </div>
            )}
            {error && <p className="rounded-2xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{error}</p>}
          </div>
          </div>
          <form onSubmit={onSubmit} className="shrink-0 pb-4 pt-3">
            <div className="flex items-end gap-2 rounded-3xl border border-line bg-white p-2 shadow-card">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    void submit(draft);
                  }
                }}
                rows={1}
                placeholder="Ask about a development, a city, or a budget"
                className="max-h-36 min-h-12 flex-1 resize-none bg-transparent px-3 py-3 outline-none"
              />
              <button
                type="submit"
                disabled={loading || !draft.trim()}
                className="mb-1 inline-flex h-11 w-11 items-center justify-center rounded-full bg-ink text-sand disabled:opacity-40"
                aria-label="Send"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="px-3 pt-2 text-xs text-mist">
              Prices and availability are a snapshot of the indexed public pages, not a live offer.
            </p>
          </form>
        </section>
      </main>
    </div>
  );
}
