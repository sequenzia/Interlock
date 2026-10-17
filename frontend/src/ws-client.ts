import { wsUrl } from "./backend-url";
import { useStore } from "./store";
import type { ClientMessage, ServerMessage } from "./types";

// One live socket at a time. Each connect() bumps the generation; a socket whose
// generation is stale (StrictMode remount, explicit disconnect) never reconnects.
let socket: WebSocket | null = null;
let generation = 0;
let retryMs = 500;

function apply(msg: ServerMessage): void {
  const s = useStore.getState();
  switch (msg.type) {
    case "hello":
      s.setHello(msg);
      s.setConstraints(msg.constraints, msg.zones);
      break;
    case "state":
      s.setSession(msg);
      break;
    case "history":
      s.replaceSteps(msg.records);
      break;
    case "step":
      s.pushStep(msg.record);
      break;
    case "escalation":
      s.setEscalation(msg.escalation);
      break;
    case "constraints":
      s.setConstraints(msg.constraints, msg.zones);
      break;
    case "metrics":
      s.setMetrics(msg);
      break;
    case "error":
      s.pushError(msg.message);
      break;
  }
}

function open(myGeneration: number): void {
  if (myGeneration !== generation) return;
  const ws = new WebSocket(wsUrl());
  socket = ws;
  ws.onopen = () => {
    if (myGeneration !== generation) {
      ws.close();
      return;
    }
    retryMs = 500;
    useStore.getState().setConnected(true);
  };
  ws.onmessage = (event: MessageEvent<string>) => {
    if (myGeneration === generation) apply(JSON.parse(event.data) as ServerMessage);
  };
  ws.onclose = () => {
    if (myGeneration !== generation) return;
    useStore.getState().setConnected(false);
    setTimeout(() => open(myGeneration), retryMs);
    retryMs = Math.min(retryMs * 2, 5000);
  };
  ws.onerror = () => ws.close();
}

export function connect(): () => void {
  const myGeneration = ++generation;
  open(myGeneration);
  return () => {
    if (myGeneration === generation) generation++;
    socket?.close();
    socket = null;
  };
}

export function send(msg: ClientMessage): void {
  if (socket?.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify(msg));
  } else {
    useStore.getState().pushError("not connected to the server");
  }
}
