import { Plus, Trash2 } from "lucide-react";
import type { SessionSummary } from "../types";

const FILTERS = [
  { id: null, label: "Both sources" },
  { id: "darglobal", label: "DarGlobal" },
  { id: "wasalt", label: "Wasalt" },
] as const;

interface SidebarProps {
  open: boolean;
  sessions: SessionSummary[];
  activeId: string | null;
  sourceFilter: string | null;
  onClose: () => void;
  onNew: () => void;
  onSelect: (id: string) => void;
  onFilter: (value: string | null) => void;
  onClear: () => void;
}

export function Sidebar({
  open,
  sessions,
  activeId,
  sourceFilter,
  onClose,
  onNew,
  onSelect,
  onFilter,
  onClear,
}: SidebarProps) {
  return (
    <>
      <div
        className={`fixed inset-0 z-30 bg-ink/40 transition lg:hidden ${open ? "opacity-100" : "pointer-events-none opacity-0"}`}
        onClick={onClose}
      />
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex h-full w-[290px] shrink-0 flex-col overflow-hidden bg-ink text-sand transition-transform lg:static lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="shrink-0 border-b border-white/10 px-6 py-7">
          <p className="text-xs uppercase tracking-[0.28em] text-gold">EstateIQ</p>
          <h1 className="mt-2 font-serif text-3xl leading-none">EstateIQ</h1>
          <p className="mt-2 text-sm text-sand/70">AI-Powered Real Estate Intelligence</p>
        </div>
        <div className="shrink-0 px-4 pt-5">
          <button
            onClick={onNew}
            className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-gold px-4 py-2.5 text-sm text-ink"
          >
            <Plus size={16} /> New conversation
          </button>
          <div className="mt-6">
            <p className="px-2 text-xs uppercase tracking-[0.18em] text-sand/50">Source</p>
            <div className="mt-2 grid gap-1">
              {FILTERS.map((filter) => (
                <button
                  key={filter.label}
                  onClick={() => onFilter(filter.id)}
                  className={`rounded-xl px-3 py-2 text-left text-sm ${
                    sourceFilter === filter.id ? "bg-white/10 text-white" : "text-sand/75 hover:bg-white/5"
                  }`}
                >
                  {filter.label}
                </button>
              ))}
            </div>
          </div>
          <p className="mb-2 mt-3 px-2 text-xs uppercase tracking-[0.18em] text-sand/50">History</p>
        </div>
        <div className="no-scrollbar min-h-0 flex-1 overflow-y-auto overscroll-contain px-4 pb-3">
          <div className="grid gap-1">
            {sessions.length === 0 && <p className="px-2 text-sm text-sand/50">No conversations yet.</p>}
            {sessions.map((session) => (
              <button
                key={session.id}
                onClick={() => onSelect(session.id)}
                className={`truncate rounded-xl px-3 py-2 text-left text-sm ${
                  activeId === session.id ? "bg-white/10" : "hover:bg-white/5"
                }`}
              >
                {session.title || "Conversation"}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={onClear}
          className="m-4 inline-flex shrink-0 items-center justify-center gap-2 rounded-full border border-white/15 px-4 py-2 text-sm text-sand/80"
        >
          <Trash2 size={15} /> Clear conversation
        </button>
      </aside>
    </>
  );
}
