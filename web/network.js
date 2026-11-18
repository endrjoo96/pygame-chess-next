(() => {
  const protocolVersion = 2;
  const messages = [];
  let socket = null;
  let intentionalClose = false;
  let viewportSyncQueued = false;

  const emit = (type, fields = {}) => messages.push({ t: type, ...fields });

  const syncViewport = () => {
    if (viewportSyncQueued) return;
    viewportSyncQueued = true;
    window.requestAnimationFrame(() => {
      viewportSyncQueued = false;
      if (typeof window_resize === "function") window_resize();
    });
  };

  window.addEventListener("resize", syncViewport, { passive: true });

  const start = (url, request) => {
    close();
    intentionalClose = false;
    const activeSocket = new WebSocket(url);
    socket = activeSocket;
    activeSocket.onopen = () => {
      if (socket === activeSocket) {
        activeSocket.send(JSON.stringify({ v: protocolVersion, ...request }));
      }
    };
    activeSocket.onmessage = event => {
      if (socket !== activeSocket) return;
      try {
        const message = JSON.parse(event.data);
        if (message.v !== protocolVersion || typeof message.t !== "string") {
          throw new Error("invalid_message");
        }
        messages.push(message);
      } catch (error) {
        emit("error", { reason: "invalid_server_message" });
      }
    };
    activeSocket.onerror = () => {
      if (socket === activeSocket) {
        emit("error", { reason: "server_connection_failed" });
      }
    };
    activeSocket.onclose = () => {
      if (socket === activeSocket && !intentionalClose) {
        emit("server_disconnected");
      }
    };
  };

  const close = () => {
    intentionalClose = true;
    messages.splice(0);
    if (socket) socket.close();
    socket = null;
  };

  window.chessNetwork = {
    startHost: url => start(url, { t: "create_room" }),
    startGuest: (url, room) => start(url, { t: "join_room", room }),
    popMessages: () => JSON.stringify(messages.splice(0)),
    sendMessage: raw => {
      if (!socket || socket.readyState !== WebSocket.OPEN) return false;
      socket.send(raw);
      return true;
    },
    syncViewport,
    copyInvite: async url => {
      try {
        await navigator.clipboard.writeText(url);
        emit("invite_copied");
      } catch (error) {
        emit("error", { reason: "clipboard_unavailable" });
      }
    },
    close
  };
})();
