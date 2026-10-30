function waitForIce(peer, signal) {
  return new Promise((resolve, reject) => {
    const finish = error => {
      clearTimeout(timer); peer.removeEventListener('icegatheringstatechange', changed);
      signal.removeEventListener('abort', aborted);
      if (error) reject(error); else resolve();
    };
    const changed = () => { if (peer.iceGatheringState === 'complete') finish(); };
    const aborted = () => finish(new Error('Video connection cancelled'));
    const timer = setTimeout(() => finish(new Error('Could not gather WebRTC candidates. Check the TURN relay.')), 15000);
    peer.addEventListener('icegatheringstatechange', changed);
    signal.addEventListener('abort', aborted, { once: true });
    if (signal.aborted) aborted(); else changed();
  });
}

export function subscribeVideo(api, sessionId, onStream, onStatus) {
  let stopped = false;
  let timer;
  let cleanup = () => {};
  let retry = 1000;
  const path = `/sessions/${sessionId}/stream`;
  async function connect() {
    if (stopped) return;
    const controller = new AbortController();
    let peer;
    let id;
    let heartbeat;
    let retired = false;
    const release = () => {
      controller.abort(); clearTimeout(watchdog); clearTimeout(heartbeat);
      peer?.close();
      if (id && api.tokens) { void api.request(`${path}/connections/${id}`, 'DELETE').catch(() => {}); id = null; }
    };
    const reconnect = error => {
      if (stopped || retired) return;
      retired = true; release(); onStream(null);
      onStatus(error?.status === 409 ? 'Waiting for the mobile WebRTC camera…' : error?.message || 'Video disconnected. Reconnecting…');
      timer = setTimeout(() => void connect(), retry); retry = Math.min(10000, retry * 2);
    };
    const watchdog = setTimeout(() => reconnect(new Error('Video connection timed out. Check the TURN relay.')), 30000);
    cleanup = () => { retired = true; release(); };
    try {
      onStatus('Connecting live video…');
      if (!globalThis.RTCPeerConnection) throw new Error('This browser does not support WebRTC video.');
      const config = await api.request(`${path}/config`, 'GET', undefined, controller.signal);
      if (stopped || retired) return;
      peer = new RTCPeerConnection({ iceServers: config.ice_servers, iceTransportPolicy: config.ice_transport_policy });
      peer.addTransceiver('video', { direction: 'recvonly' });
      peer.ontrack = event => {
        if (stopped || retired) return;
        onStream(event.streams[0] || new MediaStream([event.track]));
        event.track.onended = () => reconnect(new Error('Mobile video ended. Reconnecting…'));
      };
      peer.onconnectionstatechange = () => {
        if (stopped || retired) return;
        if (peer.connectionState === 'connected') { clearTimeout(watchdog); retry = 1000; onStatus('Live from mobile · WebRTC'); }
        if (['failed', 'closed'].includes(peer.connectionState)) reconnect(new Error('Video disconnected. Reconnecting…'));
      };
      await peer.setLocalDescription(await peer.createOffer());
      await waitForIce(peer, controller.signal);
      const answer = await api.request(`${path}/viewer/offer`, 'POST', { type: 'offer', sdp: peer.localDescription.sdp }, controller.signal);
      id = answer.connection_id;
      if (stopped || retired) { release(); return; }
      await peer.setRemoteDescription({ type: 'answer', sdp: answer.sdp });
      async function refresh() {
        try {
          await api.request(`${path}/connections/${id}/refresh`, 'POST');
          if (!stopped && !retired) heartbeat = setTimeout(() => void refresh(), 20000);
        } catch (error) { reconnect(error); }
      }
      heartbeat = setTimeout(() => void refresh(), 20000);
    } catch (error) { reconnect(error); }
  }
  void connect();
  return () => { stopped = true; clearTimeout(timer); cleanup(); onStream(null); };
}
