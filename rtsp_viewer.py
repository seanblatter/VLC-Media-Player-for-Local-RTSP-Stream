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
  <title>Local RTSP Viewer</title>
  <style>
    :root{
      --overlay-pos: center;
    }
    html, body { height: 100%; margin: 0; }
    body {
      display: grid;
      grid-template-rows: auto auto 1fr;
      background: var(--bg, #101418);
      color: #e8e8e8;
      font-family: system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, "Apple Color Emoji", "Segoe UI Emoji", "Segoe UI Symbol";
    }
    header {
      padding: 10px 14px;
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      background: rgba(0,0,0,0.25);
      backdrop-filter: blur(6px);
      position: sticky; top: 0; z-index: 10;
      border-bottom: 1px solid rgba(255,255,255,0.07);
    }
    header label { font-size: 12px; opacity: 0.9; display: flex; align-items: center; gap: 6px; }
    header input[type="text"], header input[type="password"] {
      padding: 6px 8px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(0,0,0,0.2); color: #f3f3f3; min-width: 140px; outline: none;
    }
    header select {
      padding: 6px 8px; border-radius: 8px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(0,0,0,0.2); color: #f3f3f3; outline: none;
    }
    header button {
      padding: 8px 12px; border-radius: 10px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(255,255,255,0.05); color: #fff; cursor: pointer;
    }
    .row2 {
      padding: 8px 14px; display: flex; gap: 12px; align-items: center; flex-wrap: wrap;
      border-bottom: 1px dashed rgba(255,255,255,0.07);
    }
    .badge { font-size: 11px; padding: 4px 8px; border-radius: 999px;
      border: 1px solid rgba(255,255,255,0.15); background: rgba(255,255,255,0.06); margin-left: 8px; }
    .hint { font-size: 12px; opacity: 0.8; }
    main { position: relative; overflow: hidden; }
    .stage { width: 100%; height: 100%; display: grid; place-items: center; padding: 10px; box-sizing: border-box; }
    .stage img { max-width: 100%; max-height: 100%; border-radius: 12px; box-shadow: 0 10px 30px rgba(0,0,0,0.35);
      border: 1px solid rgba(255,255,255,0.08); background: #000; }
    .overlay { position: absolute; inset: 0; pointer-events: none; display: grid; place-items: center; padding: 20px; }
    .overlay-inner {
      max-width: min(90vw, 1200px); width: 100%; text-align: center;
      font-size: clamp(18px, 4vw, 48px); font-weight: 700; line-height: 1.2;
      color: var(--text, #ffffff); text-shadow: 0 2px 10px rgba(0,0,0,0.65); white-space: pre-wrap;
    }
    .top-left    { justify-items: start; align-items: start; }
    .top-right   { justify-items: end;   align-items: start; }
    .center      { justify-items: center;align-items: center;}
    .bottom-left { justify-items: start; align-items: end;   }
    .bottom-right{ justify-items: end;   align-items: end;   }
  </style>
</head>
<body>
  <!-- Style & overlay controls -->
  <header>
    <strong>Local RTSP Viewer</strong>
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
      </select>
    </label>
    <button id="saveStyle">Save</button>
    <button id="clearStyle">Clear</button>
  </header>

  <!-- RTSP builder -->
  <div class="row2">
    <strong>RTSP Source</strong>
    <label>User <input id="u" type="text" placeholder="username" /></label>
    <label>Pass <input id="p" type="password" placeholder="password" /></label>
    <label>IP <input id="ip" type="text" placeholder="192.168.1.164" /></label>
    <label>Port <input id="port" type="text" value="554" /></label>
    <label>Path <input id="path" type="text" value="/stream1" /></label>
    <button id="saveRtsp">Use RTSP</button>
    <span class="hint">Tip: Many cameras use <code>/stream1</code> (HD) and <code>/stream2</code> (SD).</span>
  </div>

  <main>
    <div class="stage">
      <img id="feed" src="/video_feed" alt="RTSP stream" />
    </div>
    <div id="overlay" class="overlay center">
      <div id="overlayInner" class="overlay-inner"></div>
    </div>
  </main>

  <script>
    const $ = sel => document.querySelector(sel);
    const $bg = $('#bg'), $fg = $('#fg'), $text = $('#text'), $pos = $('#pos');
    const $overlay = $('#overlay'), $inner = $('#overlayInner');
    const $u = $('#u'), $p = $('#p'), $ip = $('#ip'), $port = $('#port'), $path = $('#path');
    const $feed = $('#feed');

    // ---- Style state ----
    const loadStyle = () => {
      try{
        const s = JSON.parse(localStorage.getItem('rtsp_viewer_style') || '{}');
        if (s.bg) $bg.value = s.bg, document.body.style.setProperty('--bg', s.bg);
        if (s.fg) $fg.value = s.fg, document.body.style.setProperty('--text', s.fg);
        if ('text' in s) $text.value = s.text, $inner.textContent = s.text || '';
        if (s.pos) $pos.value = s.pos, $overlay.className = 'overlay ' + s.pos;
      }catch{}
    };
    const saveStyle = () => {
      const s = { bg:$bg.value, fg:$fg.value, text:$text.value, pos:$pos.value };
      localStorage.setItem('rtsp_viewer_style', JSON.stringify(s));
      loadStyle();
    };
    const clearStyle = () => {
      localStorage.removeItem('rtsp_viewer_style');
      $bg.value = '#101418'; $fg.value = '#ffffff'; $text.value = ''; $pos.value = 'center';
      loadStyle();
    };

    // live preview
    $bg.addEventListener('input', ()=> document.body.style.setProperty('--bg', $bg.value));
    $fg.addEventListener('input', ()=> document.body.style.setProperty('--text', $fg.value));
    $text.addEventListener('input', ()=> $inner.textContent = $text.value);
    $pos.addEventListener('change', ()=> $overlay.className = 'overlay ' + $pos.value);
    $('#saveStyle').addEventListener('click', saveStyle);
    $('#clearStyle').addEventListener('click', clearStyle);

    // ---- RTSP state ----
    const buildRtsp = (u, p, ip, port, path) => {
      // Include credentials only if provided
      const auth = (u && p) ? `${encodeURIComponent(u)}:${encodeURIComponent(p)}@` : '';
      const cleanPath = path.startsWith('/') ? path : `/${path}`;
      return `rtsp://${auth}${ip}:${port}${cleanPath}`;
    };
    const loadRtsp = () => {
      try{
        const r = JSON.parse(localStorage.getItem('rtsp_viewer_rtsp') || '{}');
        if (r.u) $u.value = r.u;
        if (r.p) $p.value = r.p;
        if (r.ip) $ip.value = r.ip;
        if (r.port) $port.value = r.port;
        if (r.path) $path.value = r.path;
        if (r.src) $feed.src = `/video_feed?src=${encodeURIComponent(r.src)}`;
      }catch{}
    };
    const saveRtsp = () => {
      const src = buildRtsp($u.value.trim(), $p.value.trim(), $ip.value.trim(), $port.value.trim(), $path.value.trim());
      const r = { u:$u.value, p:$p.value, ip:$ip.value, port:$port.value, path:$path.value, src };
      localStorage.setItem('rtsp_viewer_rtsp', JSON.stringify(r));
      // point the <img> to the new source
      $feed.src = `/video_feed?src=${encodeURIComponent(src)}`;
    };
    $('#saveRtsp').addEventListener('click', saveRtsp);

    // Init
    loadStyle();
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
