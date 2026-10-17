# Socket client

`frontend/src/ws-client.ts` owns the one WebSocket between the console and the backend. It is 80 lines and has no React in it: it reads and writes the store through `useStore.getState()`, which is what lets `app.tsx` treat it as a plain effect.

## One socket, one generation

Three module-level variables hold the connection:

```typescript
let socket: WebSocket | null = null;
let generation = 0;
let retryMs = 500;
```

`connect()` increments `generation`, opens a socket tagged with that number, and returns a cleanup function. Every callback checks its own generation against the current one before doing anything:

```typescript
export function connect(): () => void {
  const myGeneration = ++generation;
  open(myGeneration);
  return () => {
    if (myGeneration === generation) generation++;
    socket?.close();
    socket = null;
  };
}
```

The counter exists for two reasons. React `StrictMode` runs every effect twice in development, mount then cleanup then mount, so without it the first socket's `onclose` would schedule a reconnect and two sockets would fight over the store. And an explicit disconnect must stop the retry loop, not just close the current socket. A socket whose generation is stale ignores messages, does not mark the store connected, and never reconnects.

## Opening and reconnecting

`open()` returns at once if its generation is stale, otherwise creates `new WebSocket(wsUrl())` with the URL from `backend-url.ts`.

| Event | Behaviour |
| --- | --- |
| `onopen` | Closes the socket if stale; otherwise resets `retryMs` to 500 and sets `connected` true |
| `onmessage` | Parses JSON and calls `apply()` when current |
| `onclose` | When current: sets `connected` false, schedules `open()` after `retryMs`, then doubles `retryMs` up to 5000 |
| `onerror` | Closes the socket, which routes through `onclose` |

So a backend restart costs one reconnect attempt at 0.5 s, then 1, 2, 4 and 5 s between attempts until it answers. The header dot in the status strip turns red while `connected` is false.

## Applying server messages

`apply()` is a `switch` over `ServerMessage["type"]`, one store action per case:

| Message | Store effect |
| --- | --- |
| `hello` | `setHello(msg)`, then `setConstraints(msg.constraints, msg.zones)` |
| `state` | `setSession(msg)`, which also detects a new run and clears a resolved escalation |
| `history` | `replaceSteps(msg.records)` |
| `step` | `pushStep(msg.record)` |
| `escalation` | `setEscalation(msg.escalation)` |
| `constraints` | `setConstraints(msg.constraints, msg.zones)` |
| `metrics` | `setMetrics(msg)` |
| `error` | `pushError(msg.message)` |

The order matters on connect. The server sends `hello`, `state`, `history`, `metrics`, and then `escalation` if one is open. `hello` arrives before `state`, so the constraints exist when `setSession` runs; `state` arrives before `history`, so the new-run check has already cleared stale steps before the real history replaces them. A refresh in the middle of an episode therefore comes back with the full timeline and, if the sim is paused on a question, the approval card. The server side is described in [Server and session](../backend/server.md) and the message shapes in [WebSocket protocol](../contracts/websocket-protocol.md).

## Sending commands

```typescript
export function send(msg: ClientMessage): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  } else {
    useStore.getState().pushError("not connected to the server");
  }
}
```

There is no queue. A command sent while disconnected is dropped and the operator sees the toast. Components call `send()` directly from event handlers; nothing is debounced here, which is why `ThresholdControls` commits on pointer up rather than on every slider move.

## types.ts is a mirror

`frontend/src/types.ts` declares `LogRecord`, `Escalation`, `SessionState`, `Metrics`, `Hello`, the `ServerMessage` and `ClientMessage` unions, and the evaluation report types. It is hand-written and must match `backend/logger.py` and `backend/server.py` field for field; the e2e test and the typecheck are the only guards. The change order from CLAUDE.md is: the log record contract first, then `backend/logger.py`, then `types.ts`. The contract is documented in [Log record](../contracts/log-record.md), and [Extending Interlock](../extending.md) walks through adding a field or a message end to end.

!!! tip "Debugging the stream"
    Every server message is plain JSON on one socket at `/ws`. The browser's network panel shows the frames in order, and the same stream is what `tests/test_server.py` reads with `websocket_connect`, so a protocol question can be answered from either side.
