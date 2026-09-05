/**
 * VoiceForm Background Service Worker (Manifest V3)
 * Provides WebSocket proxy bridge to bypass browser Mixed Content restrictions on HTTPS sites.
 */

chrome.runtime.onInstalled.addListener(() => {
  console.log('[VoiceForm] Extension installed successfully (VoiceForm Premium Engine)');
});

chrome.runtime.onConnect.addListener((port) => {
  if (port.name !== 'voiceform-ws') return;

  let socket: WebSocket | null = null;

  port.onMessage.addListener((msg: any) => {
    if (msg.type === 'CONNECT') {
      const url = msg.url || 'ws://127.0.0.1:8765/ws';
      try {
        if (socket) {
          socket.close();
        }
        socket = new WebSocket(url);

        socket.onopen = () => {
          try {
            port.postMessage({ type: '__WS_EVENT__', event: 'open' });
          } catch {
            // Port may have disconnected
          }
        };

        socket.onmessage = (evt) => {
          try {
            port.postMessage({ type: '__WS_EVENT__', event: 'message', data: evt.data });
          } catch {
            // Port disconnected
          }
        };

        socket.onclose = () => {
          try {
            port.postMessage({ type: '__WS_EVENT__', event: 'close' });
          } catch {
            // Port disconnected
          }
        };

        socket.onerror = (err) => {
          try {
            port.postMessage({ type: '__WS_EVENT__', event: 'error', error: String(err) });
          } catch {
            // Port disconnected
          }
        };
      } catch (err) {
        port.postMessage({ type: '__WS_EVENT__', event: 'error', error: String(err) });
      }
    } else if (msg.type === 'SEND') {
      if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(msg.data);
      }
    } else if (msg.type === 'DISCONNECT') {
      if (socket) {
        socket.close();
        socket = null;
      }
    }
  });

  port.onDisconnect.addListener(() => {
    if (socket) {
      socket.close();
      socket = null;
    }
  });
});
