import { useStream } from "../stores/streamStore";

/** One reconnecting WebSocket for the whole app: quotes + notifications +
 *  heartbeats. Exponential backoff 1s -> 30s; feeds the zustand stream store
 *  outside React render so panels re-render only via selectors. */
let started = false;

export function startStream(): void {
  if (started) return;
  started = true;
  let delay = 1000;

  const connect = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    useStream.getState().setStatus("connecting");
    const ws = new WebSocket(`${proto}://${location.host}/ws/stream`);

    ws.onopen = () => {
      delay = 1000;
      useStream.getState().setStatus("open");
    };
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "quotes") useStream.getState().applyQuotes(msg.data);
        else if (msg.type === "notification")
          useStream.getState().pushNotification(msg.data);
      } catch {
        /* malformed frame — ignore */
      }
    };
    ws.onclose = () => {
      useStream.getState().setStatus("closed");
      setTimeout(connect, delay);
      delay = Math.min(delay * 2, 30000);
    };
    ws.onerror = () => ws.close();
  };

  connect();
}
