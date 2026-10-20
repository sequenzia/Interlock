import { CloseIcon } from "../icons";
import { useStore } from "../store";

const ROWS: Array<[string[], string]> = [
  [["space"], "play or pause"],
  [["n"], "one step"],
  [["a"], "approve the open escalation"],
  [["d"], "deny it and run the fallback"],
  [["1", "5"], "run the candidate of that rank"],
  [["←", "→"], "move the inspector one step"],
  [["esc"], "follow live, or close this"],
  [["?"], "this list"],
];

export function ShortcutsOverlay() {
  const open = useStore((s) => s.shortcutsOpen);
  const setOpen = useStore((s) => s.setShortcutsOpen);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-zinc-950/70" onClick={() => setOpen(false)}>
      <div
        role="dialog"
        aria-label="keyboard shortcuts"
        className="enter panel w-80 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-title">
          <span>Keyboard shortcuts</span>
          <button type="button" className="btn btn-icon" aria-label="close" onClick={() => setOpen(false)}>
            <CloseIcon />
          </button>
        </div>
        <ul className="flex flex-col gap-1.5 p-3">
          {ROWS.map(([keys, what]) => (
            <li key={what} className="flex items-center justify-between gap-3 text-xs">
              <span className="text-zinc-300">{what}</span>
              <span className="flex items-center gap-1">
                {keys.map((k, i) => (
                  <span key={k} className="flex items-center gap-1">
                    {i > 0 && <span className="text-zinc-500">to</span>}
                    <kbd className="kbd">{k}</kbd>
                  </span>
                ))}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
