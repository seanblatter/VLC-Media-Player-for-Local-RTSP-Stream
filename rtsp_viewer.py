#!/usr/bin/env python3
import time
import cv2
from flask import Flask, Response, render_template_string, request

# ==== Defaults (can be overridden from UI via querystring) ====
DEFAULT_RTSP_URL = "rtsp://192.168.1.164:554/stream1"

CAPTURE_RETRY_DELAY_SEC = 2.0
JPEG_QUALITY = 80  # 0..100

app = Flask(__name__)

HTML = r"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Lettuce Stream</title>
  <style>
    :root{
      --overlay-x: 50%;
      --overlay-y: 50%;
    }
    html, body { height: 100%; margin: 0; }
    body {
      min-height: 100vh;
      display: grid;
      grid-template-columns: 1fr minmax(240px, 360px);
      grid-template-rows: auto 1fr;
      background: var(--bg, #101418);
      color: #e8e8e8;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
    }
    header {
      grid-column: 1 / -1;
      padding: 12px 16px;
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      background: rgba(0,0,0,0.25);
      backdrop-filter: blur(6px);
      border-bottom: 1px solid rgba(255,255,255,0.07);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    header .controls {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
    header label { font-size: 12px; opacity: 0.9; display: flex; align-items: center; gap: 6px; }
    header input[type="text"], header input[type="password"], .rtsp-panel input[type="text"], .rtsp-panel input[type="password"] {
      padding: 6px 8px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(0,0,0,0.2); color: #f3f3f3; min-width: 140px; outline: none;
    }
    header select {
      padding: 6px 8px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(0,0,0,0.2); color: #f3f3f3; outline: none;
    }
    header button, .rtsp-panel button {
      padding: 8px 12px; border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(255,255,255,0.05); color: #fff; cursor: pointer;
    }
    header .badge { font-size: 11px; padding: 4px 8px; border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.06); margin-left: 8px; }
    header .title {
      margin-left: auto;
      font-weight: 700;
      font-size: 18px;
      letter-spacing: 0.02em;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    main {
      grid-row: 2;
      grid-column: 1;
      position: relative;
      overflow: hidden;
      min-height: 0;
    }
    .stage {
      width: 100%;
      height: 100%;
      position: relative;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: clamp(10px, 2vw, 24px);
      box-sizing: border-box;
    }
    .stage img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: 12px;
      box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.08);
      background: #000;
    }
    .overlay {
      position: absolute;
      top: var(--overlay-y);
      left: var(--overlay-x);
      transform: translate(-50%, -50%);
      pointer-events: auto;
      cursor: grab;
      padding: 12px;
      max-width: min(90vw, 1200px);
      width: max-content;
      display: inline-flex;
      justify-content: center;
      touch-action: none;
      z-index: 1;
    }
    .overlay:active { cursor: grabbing; }
    .overlay-inner {
      width: auto;
      text-align: center;
      font-size: clamp(18px, 4vw, 48px);
      font-weight: 700;
      line-height: 1.2;
      color: var(--text, #ffffff);
      text-shadow: 0 2px 10px rgba(0,0,0,0.65);
      white-space: pre-wrap;
      user-select: none;
      pointer-events: none;
    }
    .expand-control {
      position: absolute;
      bottom: 16px;
      right: 16px;
      padding: 8px 12px;
      border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.25);
      background: rgba(0,0,0,0.45);
      color: #fff;
      font-size: 18px;
      line-height: 1;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.2s ease, transform 0.2s ease;
      pointer-events: none;
      z-index: 2;
    }
    .stage:hover .expand-control,
    .stage:focus-within .expand-control {
      opacity: 1;
      pointer-events: auto;
      transform: translateY(0);
    }
    .expand-control:focus-visible {
      outline: 2px solid rgba(255,255,255,0.75);
      outline-offset: 2px;
    }
    .stage.fullscreen-active img {
      border-radius: 0;
      box-shadow: none;
    }
    .rtsp-panel {
      grid-row: 2;
      grid-column: 2;
      background: rgba(0,0,0,0.35);
      border-left: 1px solid rgba(255,255,255,0.07);
      display: flex;
      flex-direction: column;
      max-height: 100%;
      transition: max-height 0.3s ease;
      overflow: hidden;
    }
    .rtsp-panel-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 16px 18px;
      border: none;
      background: transparent;
      color: inherit;
      font: inherit;
      cursor: pointer;
      text-align: left;
    }
    .rtsp-panel-header .chevron {
      transition: transform 0.2s ease;
    }
    .rtsp-panel.collapsed .rtsp-panel-header .chevron {
      transform: rotate(-90deg);
    }
    .panel-body {
      display: grid;
      gap: 12px;
      padding: 0 18px 18px;
      max-height: 800px;
      transition: max-height 0.3s ease, opacity 0.3s ease, padding 0.3s ease;
    }
    .rtsp-panel.collapsed .panel-body {
      max-height: 0;
      opacity: 0;
      padding: 0 18px;
      pointer-events: none;
    }
    .panel-body label {
      font-size: 12px;
      opacity: 0.9;
      display: flex;
      flex-direction: column;
      gap: 6px;
    }
    .panel-hint {
      font-size: 12px;
      opacity: 0.75;
    }
    @media (max-width: 900px) {
      body {
        grid-template-columns: 1fr;
        grid-template-rows: auto auto 1fr;
      }
      main {
        grid-row: 3;
        grid-column: 1;
      }
      .rtsp-panel {
        grid-row: 2;
        grid-column: 1;
        border-left: none;
        border-top: 1px solid rgba(255,255,255,0.07);
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="controls">
      <span class="badge">MJPEG proxy</span>
      <label>Background <input id="bg" type="color" /></label>
      <label>Text color <input id="fg" type="color" value="#ffffff" /></label>
      <label>Overlay text <input id="text" type="text" placeholder="Type overlay text…" /></label>
      <label>Position
        <select id="pos">
          <option value="center">Center</option>
          <option value="top-left">Top-Left</option>
          <option value="top-right">Top-Right</option>
          <option value="bottom-left">Bottom-Left</option>
          <option value="bottom-right">Bottom-Right</option>
          <option value="custom">Custom (drag)</option>
        </select>
      </label>
      <button id="saveStyle">Save</button>
      <button id="clearStyle">Clear</button>
    </div>
    <span class="title">Lettuce Stream 🥬</span>
  </header>

  <main>
    <div class="stage" id="stage">
      <img id="feed" src="/video_feed" alt="RTSP stream" />
      <button id="expandToggle" class="expand-control" type="button" aria-label="Toggle fullscreen">⤢</button>
      <div id="overlay" class="overlay">
        <div id="overlayInner" class="overlay-inner"></div>
      </div>
    </div>
  </main>

  <aside class="rtsp-panel" id="rtspPanel">
    <button class="rtsp-panel-header" type="button" id="rtspPanelToggle">
      <span class="panel-title">Lettuce Stream 🥬</span>
      <span class="chevron">⌄</span>
    </button>
    <div class="panel-body">
      <label>User
        <input id="u" type="text" placeholder="username" />
      </label>
      <label>Pass
        <input id="p" type="password" placeholder="password" />
      </label>
      <label>IP
        <input id="ip" type="text" placeholder="192.168.1.164" />
      </label>
      <label>Port
        <input id="port" type="text" value="554" />
      </label>
      <label>Path
        <input id="path" type="text" value="/stream1" />
      </label>
      <button id="saveRtsp">Save</button>
      <span class="panel-hint">Tip: Many cameras use <code>/stream1</code> (HD) and <code>/stream2</code> (SD).</span>
    </div>
  </aside>

  <script>
    const $ = sel => document.querySelector(sel);
    const $bg = $('#bg'), $fg = $('#fg'), $text = $('#text'), $pos = $('#pos');
    const $overlay = $('#overlay'), $inner = $('#overlayInner');
    const $stage = $('#stage');
    const $expand = $('#expandToggle');
    const $rtspPanel = $('#rtspPanel');
    const $rtspToggle = $('#rtspPanelToggle');
    const $u = $('#u'), $p = $('#p'), $ip = $('#ip'), $port = $('#port'), $path = $('#path');
    const $feed = $('#feed');
    const root = document.documentElement;

    const DEFAULTS = { bg: '#101418', fg: '#ffffff', posX: 50, posY: 50 };
    const presetPositions = {
      'center': { x: 50, y: 50 },
      'top-left': { x: 12, y: 12 },
      'top-right': { x: 88, y: 12 },
      'bottom-left': { x: 12, y: 88 },
      'bottom-right': { x: 88, y: 88 }
    };

    let overlayPos = { x: DEFAULTS.posX, y: DEFAULTS.posY };

    const applyOverlayPosition = () => {
      root.style.setProperty('--overlay-x', `${overlayPos.x}%`);
      root.style.setProperty('--overlay-y', `${overlayPos.y}%`);
    };

    const setOverlayFromPreset = value => {
      if (presetPositions[value]) {
        overlayPos = { ...presetPositions[value] };
        applyOverlayPosition();
      }
    };

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);

    const updateOverlayFromPointer = (clientX, clientY) => {
      if (!$stage) return;
      const rect = $stage.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = ((clientX - rect.left) / rect.width) * 100;
      const y = ((clientY - rect.top) / rect.height) * 100;
      overlayPos = {
        x: clamp(x, 2, 98),
        y: clamp(y, 2, 98)
      };
      applyOverlayPosition();
      if ($pos.value !== 'custom') {
        $pos.value = 'custom';
      }
    };

    if ($overlay) {
      let dragging = false;
      $overlay.addEventListener('pointerdown', event => {
        dragging = true;
        try { $overlay.setPointerCapture(event.pointerId); } catch (_) {}
        $overlay.dataset.dragging = 'true';
        updateOverlayFromPointer(event.clientX, event.clientY);
        event.preventDefault();
      });
      const endDrag = event => {
        if (!dragging) return;
        dragging = false;
        try { $overlay.releasePointerCapture(event.pointerId); } catch (_) {}
        delete $overlay.dataset.dragging;
      };
      $overlay.addEventListener('pointermove', event => {
        if (!dragging) return;
        updateOverlayFromPointer(event.clientX, event.clientY);
      });
      $overlay.addEventListener('pointerup', endDrag);
      $overlay.addEventListener('pointercancel', endDrag);
    }

    // ---- Style state ----
    const loadStyle = () => {
      overlayPos = { x: DEFAULTS.posX, y: DEFAULTS.posY };
      $bg.value = DEFAULTS.bg;
      $fg.value = DEFAULTS.fg;
      $text.value = '';
      $pos.value = 'center';
      try {
        const s = JSON.parse(localStorage.getItem('rtsp_viewer_style') || '{}');
        if (s.bg) $bg.value = s.bg;
        if (s.fg) $fg.value = s.fg;
        if ('text' in s) $text.value = s.text || '';
        if (s.pos === 'custom' && typeof s.posX === 'number' && typeof s.posY === 'number') {
          overlayPos = { x: s.posX, y: s.posY };
          $pos.value = 'custom';
        } else if (s.pos && presetPositions[s.pos]) {
          $pos.value = s.pos;
          overlayPos = { ...presetPositions[s.pos] };
        }
        if (typeof s.posX === 'number' && typeof s.posY === 'number' && $pos.value === 'custom') {
          overlayPos = { x: s.posX, y: s.posY };
        }
      } catch (_) {}
      document.body.style.setProperty('--bg', $bg.value);
      document.body.style.setProperty('--text', $fg.value);
      $inner.textContent = $text.value;
      applyOverlayPosition();
    };
    const saveStyle = () => {
      const s = {
        bg: $bg.value,
        fg: $fg.value,
        text: $text.value,
        pos: $pos.value,
        posX: overlayPos.x,
        posY: overlayPos.y
      };
      localStorage.setItem('rtsp_viewer_style', JSON.stringify(s));
      loadStyle();
    };
    const clearStyle = () => {
      localStorage.removeItem('rtsp_viewer_style');
      overlayPos = { x: DEFAULTS.posX, y: DEFAULTS.posY };
      $bg.value = DEFAULTS.bg;
      $fg.value = DEFAULTS.fg;
      $text.value = '';
      $pos.value = 'center';
      document.body.style.setProperty('--bg', DEFAULTS.bg);
      document.body.style.setProperty('--text', DEFAULTS.fg);
      $inner.textContent = '';
      applyOverlayPosition();
    };

    // live preview
    $bg.addEventListener('input', () => document.body.style.setProperty('--bg', $bg.value));
    $fg.addEventListener('input', () => document.body.style.setProperty('--text', $fg.value));
    $text.addEventListener('input', () => $inner.textContent = $text.value);
    $pos.addEventListener('change', () => {
      if ($pos.value === 'custom') return;
      setOverlayFromPreset($pos.value);
    });
    $('#saveStyle').addEventListener('click', saveStyle);
    $('#clearStyle').addEventListener('click', clearStyle);

    // ---- Fullscreen control ----
    const updateFullscreenState = () => {
      if (!$stage || !$expand) return;
      const fullscreenEl = document.fullscreenElement || document.webkitFullscreenElement;
      const isFullscreen = fullscreenEl === $stage;
      $stage.classList.toggle('fullscreen-active', isFullscreen);
      $expand.textContent = isFullscreen ? '⤡' : '⤢';
      $expand.setAttribute('aria-label', isFullscreen ? 'Exit fullscreen' : 'Enter fullscreen');
    };
    const toggleFullscreen = () => {
      if (!$stage) return;
      const fullscreenEl = document.fullscreenElement || document.webkitFullscreenElement;
      if (fullscreenEl === $stage) {
        if (document.exitFullscreen) {
          document.exitFullscreen();
        } else if (document.webkitExitFullscreen) {
          document.webkitExitFullscreen();
        }
      } else {
        if ($stage.requestFullscreen) {
          $stage.requestFullscreen();
        } else if ($stage.webkitRequestFullscreen) {
          $stage.webkitRequestFullscreen();
        }
      }
    };
    if ($expand) {
      $expand.addEventListener('click', toggleFullscreen);
    }
    document.addEventListener('fullscreenchange', updateFullscreenState);
    document.addEventListener('webkitfullscreenchange', updateFullscreenState);

    // ---- RTSP state ----
    const setPanelCollapsed = collapsed => {
      if (!$rtspPanel) return;
      $rtspPanel.classList.toggle('collapsed', collapsed);
    };
    const buildRtsp = (u, p, ip, port, path) => {
      const auth = (u && p) ? `${encodeURIComponent(u)}:${encodeURIComponent(p)}@` : '';
      const cleanPath = path.startsWith('/') ? path : `/${path}`;
      return `rtsp://${auth}${ip}:${port}${cleanPath}`;
    };
    const loadRtsp = () => {
      let hasSource = false;
      try {
        const r = JSON.parse(localStorage.getItem('rtsp_viewer_rtsp') || '{}');
        if (r.u) $u.value = r.u;
        if (r.p) $p.value = r.p;
        if (r.ip) $ip.value = r.ip;
        if (r.port) $port.value = r.port;
        if (r.path) $path.value = r.path;
        if (r.src) {
          $feed.src = `/video_feed?src=${encodeURIComponent(r.src)}`;
          hasSource = true;
        }
      } catch (_) {}
      setPanelCollapsed(hasSource);
    };
    const saveRtsp = () => {
      const src = buildRtsp($u.value.trim(), $p.value.trim(), $ip.value.trim(), $port.value.trim(), $path.value.trim());
      const r = { u: $u.value, p: $p.value, ip: $ip.value, port: $port.value, path: $path.value, src };
      localStorage.setItem('rtsp_viewer_rtsp', JSON.stringify(r));
      $feed.src = `/video_feed?src=${encodeURIComponent(src)}`;
      setPanelCollapsed(true);
    };
    $('#saveRtsp').addEventListener('click', saveRtsp);
    $rtspToggle.addEventListener('click', () => {
      const collapsed = $rtspPanel.classList.toggle('collapsed');
      if (!collapsed && $u && typeof $u.focus === 'function') {
        setTimeout(() => {
          try {
            $u.focus({ preventScroll: true });
          } catch (_) {
            $u.focus();
          }
        }, 50);
      }
    });

    // Init
    loadStyle();
    updateFullscreenState();
    loadRtsp();
  </script>
</body>
</html>
"""

def open_capture(rtsp_url: str):
    cap = None
    while cap is None or not cap.isOpened():
        if cap is not None:
            try: cap.release()
            except Exception: pass
        cap = cv2.VideoCapture(rtsp_url)
        if not cap.isOpened():
            print(f"[warn] Unable to open RTSP source, retrying in {CAPTURE_RETRY_DELAY_SEC}s: {rtsp_url}")
            time.sleep(CAPTURE_RETRY_DELAY_SEC)
        else:
            print("[info] RTSP capture opened.")
            break
    return cap

def mjpeg_generator(rtsp_url: str):
    encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), int(JPEG_QUALITY)]
    cap = open_capture(rtsp_url)
    while True:
        ok, frame = cap.read()
        if not ok or frame is None:
            try: cap.release()
            except Exception: pass
            print("[warn] Frame read failed, attempting to reopen...")
            time.sleep(CAPTURE_RETRY_DELAY_SEC)
            cap = open_capture(rtsp_url)
            continue
        ok, buf = cv2.imencode('.jpg', frame, encode_param)
        if not ok:
            continue
        jpg = buf.tobytes()
        yield (b"--frame\r\n"
               b"Content-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")

@app.route("/")
def index():
    return render_template_string(HTML)

@app.route("/video_feed")
def video_feed():
    src = request.args.get("src", DEFAULT_RTSP_URL)
    print(f"[info] /video_feed using: {src}")
    return Response(mjpeg_generator(src),
                    mimetype="multipart/x-mixed-replace; boundary=frame")

if __name__ == "__main__":
    print("Starting server at http://127.0.0.1:5000/")
    print(f"Default RTSP source: {DEFAULT_RTSP_URL}")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
