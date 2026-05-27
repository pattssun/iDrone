// Reconnecting WebSocket helper. Exponential backoff capped at 4s.
// Token is read from the page URL so callers don't have to thread it through.

export function getToken() {
  return new URLSearchParams(location.search).get("t") || "";
}

export function connect({ role, onOpen, onClose, onMessage, onState }) {
  const token = getToken();
  const proto = location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${location.host}/ws/${role}?t=${encodeURIComponent(token)}`;

  let ws = null;
  let alive = true;
  let attempt = 0;
  let backoffTimer = null;

  function setState(s) {
    if (onState) onState(s);
  }

  function send(data) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    const payload = typeof data === "string" ? data : JSON.stringify(data);
    ws.send(payload);
    return true;
  }

  function open() {
    if (!alive) return;
    setState("linking");
    ws = new WebSocket(url);
    ws.onopen = () => {
      attempt = 0;
      setState("live");
      if (onOpen) onOpen();
    };
    ws.onmessage = (ev) => {
      if (onMessage) {
        try {
          onMessage(JSON.parse(ev.data));
        } catch {
          /* ignore non-JSON */
        }
      }
    };
    ws.onclose = () => {
      if (onClose) onClose();
      if (!alive) return;
      const delay = Math.min(500 * 2 ** attempt, 4000);
      attempt++;
      setState("linking");
      backoffTimer = setTimeout(open, delay);
    };
    ws.onerror = () => {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    };
  }

  open();

  return {
    send,
    close() {
      alive = false;
      if (backoffTimer) clearTimeout(backoffTimer);
      if (ws) ws.close();
      setState("dropped");
    },
  };
}
