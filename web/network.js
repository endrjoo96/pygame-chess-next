(() => {
  const protocolVersion = 1;
  const messages = [];
  let socket = null;
  let connection = null;
  let channel = null;
  let intentionalClose = false;
  let pendingCandidates = [];

  const emit = (type, fields = {}) => messages.push({ t: type, ...fields });

  const sendSignal = (type, fields = {}) => {
    if (!socket || socket.readyState !== WebSocket.OPEN) {
      emit("error", { reason: "signaling_disconnected" });
      return;
    }
    socket.send(JSON.stringify({ v: protocolVersion, t: type, ...fields }));
  };

  const configureChannel = dataChannel => {
    channel = dataChannel;
    channel.onopen = () => {
      if (channel === dataChannel && !intentionalClose) emit("connected");
    };
    channel.onclose = () => {
      if (channel === dataChannel && !intentionalClose) emit("peer_disconnected");
    };
    channel.onerror = () => {
      if (channel === dataChannel && !intentionalClose) {
        emit("error", { reason: "data_channel_error" });
      }
    };
    channel.onmessage = event => {
      if (channel !== dataChannel || intentionalClose) return;
      try {
        const message = JSON.parse(event.data);
        if (message.v !== protocolVersion || typeof message.t !== "string") {
          throw new Error("invalid_message");
        }
        messages.push(message);
      } catch (error) {
        emit("error", { reason: "invalid_peer_message" });
      }
    };
  };

  const createConnection = () => {
    if (connection) return connection;
    const peer = new RTCPeerConnection({
      iceServers: [{ urls: "stun:stun.l.google.com:19302" }]
    });
    connection = peer;
    peer.onicecandidate = event => {
      if (event.candidate) sendSignal("ice", { candidate: event.candidate.toJSON() });
    };
    peer.ondatachannel = event => configureChannel(event.channel);
    peer.onconnectionstatechange = () => {
      if (connection !== peer) return;
      if (peer.connectionState === "failed") {
        emit("error", { reason: "peer_connection_failed" });
      } else if (peer.connectionState === "disconnected") {
        emit("peer_disconnected");
      }
    };
    return peer;
  };

  const addRemoteCandidate = async candidate => {
    if (!connection || !connection.remoteDescription) {
      pendingCandidates.push(candidate);
      return;
    }
    await connection.addIceCandidate(candidate);
  };

  const flushCandidates = async () => {
    const candidates = pendingCandidates;
    pendingCandidates = [];
    for (const candidate of candidates) {
      await connection.addIceCandidate(candidate);
    }
  };

  const receiveSignal = async message => {
    try {
      if (message.v !== protocolVersion || typeof message.t !== "string") {
        throw new Error("invalid_message");
      }
      if (message.t === "room_created" || message.t === "room_joined") {
        emit(message.t, { room: message.room, seed: message.seed });
      } else if (message.t === "peer_joined") {
        const peer = createConnection();
        configureChannel(peer.createDataChannel("chess-actions", { ordered: true }));
        const offer = await peer.createOffer();
        await peer.setLocalDescription(offer);
        sendSignal("offer", { description: peer.localDescription });
      } else if (message.t === "offer") {
        const peer = createConnection();
        await peer.setRemoteDescription(message.description);
        await flushCandidates();
        const answer = await peer.createAnswer();
        await peer.setLocalDescription(answer);
        sendSignal("answer", { description: peer.localDescription });
      } else if (message.t === "answer") {
        await connection.setRemoteDescription(message.description);
        await flushCandidates();
      } else if (message.t === "ice") {
        await addRemoteCandidate(message.candidate);
      } else if (message.t === "peer_left") {
        emit("peer_disconnected");
      } else if (message.t === "error") {
        emit("error", { reason: message.reason || "signaling_error" });
      }
    } catch (error) {
      emit("error", { reason: "webrtc_negotiation_failed" });
    }
  };

  const start = (url, request) => {
    close();
    intentionalClose = false;
    socket = new WebSocket(url);
    socket.onopen = () => {
      socket.send(JSON.stringify({ v: protocolVersion, ...request }));
    };
    socket.onmessage = event => {
      try {
        void receiveSignal(JSON.parse(event.data));
      } catch (error) {
        emit("error", { reason: "invalid_signaling_message" });
      }
    };
    socket.onerror = () => emit("error", { reason: "signaling_connection_failed" });
    socket.onclose = () => {
      if (!intentionalClose) emit("signaling_disconnected");
    };
  };

  const close = () => {
    intentionalClose = true;
    messages.splice(0);
    if (channel) channel.close();
    if (connection) connection.close();
    if (socket) socket.close();
    channel = null;
    connection = null;
    socket = null;
    pendingCandidates = [];
  };

  window.chessNetwork = {
    startHost: (url, seed) => start(url, { t: "create_room", seed }),
    startGuest: (url, room) => start(url, { t: "join_room", room }),
    popMessages: () => JSON.stringify(messages.splice(0)),
    sendMessage: raw => {
      if (!channel || channel.readyState !== "open") return false;
      channel.send(raw);
      return true;
    },
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
