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
    @import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Lora:wght@400;600&family=Outfit:wght@400;600;700&family=Space+Grotesk:wght@400;600&display=swap');
    :root {
      --bg: #101418;
      --panel-bg: rgba(10, 12, 18, 0.55);
      --panel-border: rgba(255, 255, 255, 0.08);
      --panel-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
    }
    html, body { height: 100%; margin: 0; }
    body {
      min-height: 100vh;
      display: grid;
      grid-template-columns: minmax(280px, 320px) 1fr;
      grid-template-rows: auto 1fr;
      background: radial-gradient(circle at top, rgba(58,107,255,0.12), transparent 55%), var(--bg, #101418);
      color: #f1f4f9;
      font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      transition: grid-template-columns 0.3s ease;
    }
    body.panel-collapsed {
      grid-template-columns: 0 1fr;
    }
    header {
      grid-column: 1 / -1;
      padding: 18px 26px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      background: rgba(12, 16, 25, 0.4);
      backdrop-filter: blur(18px);
      border-bottom: 1px solid rgba(255,255,255,0.08);
      position: sticky;
      top: 0;
      z-index: 10;
    }
    .title-trigger {
      appearance: none;
      border: none;
      background: rgba(255,255,255,0.04);
      color: inherit;
      font: inherit;
      font-weight: 700;
      font-size: clamp(22px, 2.8vw, 32px);
      letter-spacing: 0.015em;
      display: inline-flex;
      align-items: center;
      gap: 8px;
      cursor: pointer;
      padding: 10px 16px;
      border-radius: 999px;
      transition: background 0.2s ease, transform 0.2s ease;
    }
    .title-trigger:hover,
    .title-trigger:focus-visible {
      background: rgba(255,255,255,0.12);
      outline: none;
      transform: translateY(-1px);
    }
    .title-trigger .brand-suffix::before {
      content: attr(data-prefix);
      display: inline;
    }
    .title-trigger .brand-suffix:empty::before {
      content: '';
    }
    .brand-suffix {
      color: #9cf8d7;
      display: inline-flex;
      align-items: center;
      gap: 6px;
    }
    .menu-hint {
      flex: 1 1 100%;
      font-size: 13px;
      opacity: 0.72;
      padding-left: 4px;
      transition: opacity 0.3s ease, transform 0.3s ease;
    }
    .menu-hint.is-hidden {
      opacity: 0;
      transform: translateY(-6px);
      pointer-events: none;
    }
    main {
      grid-row: 2;
      grid-column: 2;
      position: relative;
      overflow: hidden;
      min-height: 0;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: clamp(20px, 6vh, 60px) clamp(16px, 5vw, 80px);
    }
    body.panel-collapsed main {
      grid-column: 1 / span 2;
    }
    .stream-frame {
      position: absolute;
      top: clamp(40px, 18vh, 120px);
      left: 50%;
      width: min(82vw, 1200px);
      height: min(70vh, 720px);
      display: block;
      border-radius: 28px;
      background: rgba(15,20,30,0.45);
      box-shadow: 0 40px 90px rgba(0,0,0,0.6);
      border: 1px solid rgba(255,255,255,0.06);
      overflow: visible;
    }
    .stage {
      position: relative;
      width: 100%;
      height: 100%;
      display: flex;
      align-items: center;
      justify-content: center;
      background: rgba(5, 7, 12, 0.65);
      border-radius: inherit;
      overflow: hidden;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.05);
      backdrop-filter: blur(4px);
      min-width: 220px;
      min-height: 160px;
    }
    .stage img {
      width: 100%;
      height: 100%;
      object-fit: contain;
      border-radius: inherit;
      background: #000;
    }
    .frame-handle {
      position: absolute;
      top: 14px;
      left: 14px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 8px 16px;
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      cursor: grab;
      background: linear-gradient(135deg, rgba(95,167,255,0.45), rgba(83,214,162,0.32));
      border-radius: 999px;
      border: 1px solid rgba(170,222,255,0.55);
      user-select: none;
      z-index: 3;
      color: #eff7ff;
      box-shadow: 0 18px 40px rgba(0,0,0,0.4);
    }
    .frame-handle:active {
      cursor: grabbing;
    }
    .frame-resizer {
      position: absolute;
      right: -12px;
      bottom: -12px;
      width: 28px;
      height: 28px;
      border-radius: 10px;
      border: 1px solid rgba(142,209,255,0.45);
      background: rgba(15, 24, 38, 0.85);
      cursor: nwse-resize;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 13px;
      color: #bfe7ff;
      user-select: none;
      z-index: 3;
      box-shadow: 0 18px 42px rgba(0,0,0,0.45);
    }
    .overlay-layer {
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 4;
    }
    .overlay-item {
      position: absolute;
      pointer-events: auto;
      cursor: grab;
      padding: 12px 18px;
      max-width: min(90vw, 1200px);
      transform: translate(-50%, -50%);
      display: inline-flex;
      align-items: center;
      justify-content: center;
      touch-action: none;
      filter: drop-shadow(0 18px 45px rgba(0,0,0,0.55));
      border-radius: 22px;
      background: rgba(0,0,0,0.18);
      backdrop-filter: blur(2px);
    }
    .overlay-item:active { cursor: grabbing; }
    .overlay-item__inner {
      width: auto;
      text-align: center;
      font-size: clamp(18px, 4vw, 52px);
      font-weight: 600;
      line-height: 1.25;
      color: #ffffff;
      text-shadow: 0 8px 26px rgba(0,0,0,0.65);
      white-space: pre-wrap;
      user-select: none;
      pointer-events: none;
    }
    .expand-control {
      position: absolute;
      bottom: 16px;
      right: 16px;
      padding: 8px 14px;
      border-radius: 999px;
      border: 1px solid rgba(95,167,255,0.35);
      background: rgba(12, 18, 28, 0.75);
      color: #e8f4ff;
      font-size: 18px;
      line-height: 1;
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.2s ease, transform 0.2s ease;
      pointer-events: none;
      z-index: 2;
      box-shadow: 0 16px 35px rgba(0,0,0,0.45);
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
    .control-panel {
      grid-row: 2;
      grid-column: 1;
      background: var(--panel-bg);
      border-right: 1px solid var(--panel-border);
      display: flex;
      flex-direction: column;
      max-height: 100%;
      transition: transform 0.3s ease, opacity 0.3s ease;
      overflow: hidden;
      backdrop-filter: blur(22px);
      box-shadow: var(--panel-shadow);
    }
    .control-panel.collapsed {
      transform: translateX(-100%);
      opacity: 0;
      pointer-events: none;
    }
    .panel-scroll {
      padding: 26px 24px;
      overflow-y: auto;
      display: grid;
      gap: 24px;
    }
    .panel-section {
      background: rgba(14, 18, 28, 0.72);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 20px;
      overflow: hidden;
      box-shadow: 0 26px 60px rgba(0,0,0,0.45);
    }
    .panel-section summary {
      list-style: none;
      cursor: pointer;
      padding: 18px 22px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .panel-section summary::-webkit-details-marker { display: none; }
    .panel-section[open] summary .chevron { transform: rotate(180deg); }
    .panel-section .chevron { transition: transform 0.2s ease; }
    .panel-section .section-body {
      display: grid;
      gap: 16px;
      padding: 0 22px 22px;
    }
    .panel-section label {
      font-size: 13px;
      opacity: 0.92;
      display: flex;
      flex-direction: column;
      gap: 6px;
      letter-spacing: 0.015em;
    }
    .panel-section input[type="text"],
    .panel-section input[type="password"],
    .panel-section input[type="color"],
    .panel-section select {
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(255,255,255,0.18);
      background: rgba(8, 10, 16, 0.55);
      color: #f7f8fb;
      outline: none;
      font-family: inherit;
    }
    .panel-section input[type="text"]::placeholder {
      color: rgba(247,248,251,0.45);
    }
    .panel-section button {
      padding: 10px 16px;
      border-radius: 14px;
      border: 1px solid rgba(255,255,255,0.18);
      background: linear-gradient(135deg, rgba(95,167,255,0.35), rgba(83,214,162,0.25));
      color: #fff;
      cursor: pointer;
      font-weight: 600;
      letter-spacing: 0.01em;
      transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .panel-section button:hover,
    .panel-section button:focus-visible {
      transform: translateY(-1px);
      box-shadow: 0 12px 30px rgba(95,167,255,0.35);
      outline: none;
    }
    .section-actions {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .panel-hint {
      font-size: 12px;
      opacity: 0.8;
      line-height: 1.5;
    }
    .subheading {
      font-size: 14px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.2em;
      opacity: 0.7;
    }
    .overlay-list {
      display: grid;
      gap: 16px;
    }
    .overlay-card {
      background: rgba(9, 12, 18, 0.7);
      border: 1px solid rgba(255,255,255,0.1);
      border-radius: 16px;
      padding: 16px;
      display: grid;
      gap: 12px;
      position: relative;
    }
    .overlay-card__header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      font-weight: 600;
      letter-spacing: 0.02em;
    }
    .overlay-remove {
      appearance: none;
      border: none;
      background: rgba(255,255,255,0.08);
      color: #fff;
      padding: 6px 10px;
      border-radius: 999px;
      cursor: pointer;
      font-size: 13px;
      transition: background 0.2s ease, transform 0.2s ease;
    }
    .overlay-remove:hover,
    .overlay-remove:focus-visible {
      background: rgba(255,92,120,0.3);
      transform: translateY(-1px);
      outline: none;
    }
    .overlay-add {
      background: rgba(95,167,255,0.2);
      border: 1px dashed rgba(142,209,255,0.55);
      color: #e8f4ff;
    }
    .overlay-add:hover,
    .overlay-add:focus-visible {
      box-shadow: 0 12px 30px rgba(95,167,255,0.25);
    }
    .stream-frame.fullscreen-mode .frame-handle,
    .stream-frame.fullscreen-mode .frame-resizer {
      display: none;
    }
    .stage.fullscreen-active ~ .frame-resizer,
    .stage.fullscreen-active ~ .frame-handle {
      display: none;
    }
    @media (max-width: 900px) {
      body {
        grid-template-columns: 1fr;
        grid-template-rows: auto 1fr;
      }
      header {
        justify-content: center;
        text-align: center;
        gap: 8px;
      }
      main {
        grid-column: 1;
        padding: clamp(16px, 6vh, 40px) clamp(12px, 8vw, 32px);
      }
      .control-panel {
        grid-column: 1;
        grid-row: 2;
        max-height: 360px;
      }
      body.panel-collapsed {
        grid-template-rows: auto 1fr;
      }
      body.panel-collapsed main {
        grid-row: 2;
      }
      .stream-frame {
        left: 50%;
      }
    }
    .sticker-layer {
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 2;
    }
    .sticker {
      position: absolute;
      transform: translate(-50%, -50%);
      pointer-events: auto;
      cursor: grab;
      max-width: 40vw;
      max-height: 40vh;
      box-shadow: 0 22px 50px rgba(0,0,0,0.45);
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid rgba(142,209,255,0.35);
      background: rgba(12, 18, 28, 0.75);
      touch-action: none;
    }
    .sticker:active { cursor: grabbing; }
    .sticker img {
      display: block;
      width: 100%;
      height: auto;
      pointer-events: none;
    }
    .sticker-remove {
      position: absolute;
      top: 6px;
      right: 6px;
      border: 1px solid rgba(255,255,255,0.35);
      background: rgba(0,0,0,0.6);
      color: #f7f8fb;
      width: 22px;
      height: 22px;
      border-radius: 999px;
      font-size: 14px;
      line-height: 1;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
    }
    .panel-section input[type="file"] {
      border: 1px dashed rgba(255,255,255,0.3);
      padding: 12px;
      border-radius: 12px;
      background: rgba(8, 10, 16, 0.55);
      color: #f7f8fb;
    }
    .panel-section label.checkbox {
      flex-direction: row;
      align-items: center;
      gap: 8px;
    }
  </style>
</head>
<body>
  <header>
    <button class="title-trigger" id="menuToggle" type="button" aria-expanded="true" aria-controls="rtspPanel">
      <span class="brand-name" id="brandName">Lettuce Stream</span>
      <span class="brand-suffix" id="brandSuffix" data-prefix=" "></span>
    </button>
    <span class="menu-hint" id="menuHint">Tap to open your creative studio ✨</span>
  </header>

  <aside class="control-panel" id="rtspPanel">
    <div class="panel-scroll">
      <details class="panel-section" open>
        <summary>
          <span>Appearance</span>
          <span class="chevron">⌄</span>
        </summary>
        <div class="section-body">
          <label>Background <input id="bg" type="color" /></label>
          <label>Default overlay color <input id="fg" type="color" value="#ffffff" /></label>
          <label>Default font
            <select id="fontDefault">
              <option value="outfit">Outfit — Modern</option>
              <option value="spaceGrotesk">Space Grotesk — Tech</option>
              <option value="bebas">Bebas Neue — Bold</option>
              <option value="lora">Lora — Elegant Serif</option>
              <option value="system">System Sans — Clean</option>
            </select>
          </label>
          <div class="subheading">Overlay texts ✨</div>
          <div class="overlay-list" id="overlayList"></div>
          <button type="button" id="addOverlay" class="overlay-add">➕ Add overlay text</button>
          <label>Header name <input id="headerSuffix" type="text" placeholder="Add your name" /></label>
          <label class="checkbox"><input id="showEmoji" type="checkbox" checked /> Show lettuce emoji</label>
          <label>Sticker upload <input id="stickerUpload" type="file" accept="image/*" /></label>
          <div class="section-actions">
            <button id="saveStyle" type="button">Save look</button>
            <button id="clearStyle" type="button">Reset</button>
            <button id="clearStickers" type="button">Clear stickers</button>
          </div>
          <span class="panel-hint">Tip: Drag overlays or stickers anywhere over the stage for pixel-perfect placement.</span>
        </div>
      </details>
      <details class="panel-section" open>
        <summary>
          <span>Stream source</span>
          <span class="chevron">⌄</span>
        </summary>
        <div class="section-body">
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
          <div class="section-actions">
            <button id="saveRtsp" type="button">Save</button>
          </div>
          <span class="panel-hint">Tip: Many cameras use <code>/stream1</code> (HD) and <code>/stream2</code> (SD).</span>
        </div>
      </details>
    </div>
  </aside>

  <main>
    <div class="stream-frame" id="streamFrame">
      <div class="frame-handle" id="frameHandle" title="Drag to move stream">⋮⋮</div>
      <div class="stage" id="stage">
        <img id="feed" src="/video_feed" alt="RTSP stream" />
        <div class="overlay-layer" id="overlayLayer"></div>
        <div class="sticker-layer" id="stickerLayer"></div>
        <button id="expandToggle" class="expand-control" type="button" aria-label="Toggle fullscreen">⤢</button>
      </div>
      <div class="frame-resizer" id="frameResizer" title="Drag to resize">⤢</div>
    </div>
  </main>

  <script>
    const $ = sel => document.querySelector(sel);
    const $bg = $('#bg');
    const $fg = $('#fg');
    const $fontDefault = $('#fontDefault');
    const $overlayList = $('#overlayList');
    const $addOverlay = $('#addOverlay');
    const $overlayLayer = $('#overlayLayer');
    const $stage = $('#stage');
    const $expand = $('#expandToggle');
    const $rtspPanel = $('#rtspPanel');
    const $menuToggle = $('#menuToggle');
    const $menuHint = $('#menuHint');
    const $brandSuffixEl = $('#brandSuffix');
    const $headerSuffix = $('#headerSuffix');
    const $showEmoji = $('#showEmoji');
    const $stickerUpload = $('#stickerUpload');
    const $stickerLayer = $('#stickerLayer');
    const $clearStickers = $('#clearStickers');
    const $u = $('#u'), $p = $('#p'), $ip = $('#ip'), $port = $('#port'), $path = $('#path');
    const $feed = $('#feed');
    const $frame = $('#streamFrame');
    const $frameHandle = $('#frameHandle');
    const $frameResizer = $('#frameResizer');
    const $main = document.querySelector('main');
    const overlayArea = $stage || $main || document.body;

    const DEFAULTS = { bg: '#101418', fg: '#ffffff', font: 'outfit' };
    const BRANDING_DEFAULTS = { suffix: '', showEmoji: true };
    const BRANDING_KEY = 'rtsp_viewer_branding';
    const APPEARANCE_KEY = 'rtsp_viewer_appearance_v2';
    const OVERLAY_KEY = 'rtsp_viewer_overlays_v2';
    const LEGACY_STYLE_KEY = 'rtsp_viewer_style';
    const HINT_KEY = 'rtsp_viewer_hint_dismissed';
    const STICKER_KEY = 'rtsp_viewer_stickers';

    const FONT_CHOICES = {
      outfit: { label: 'Outfit — Modern', stack: '"Outfit", "Segoe UI", sans-serif' },
      spaceGrotesk: { label: 'Space Grotesk — Tech', stack: '"Space Grotesk", "Segoe UI", sans-serif' },
      bebas: { label: 'Bebas Neue — Bold', stack: '"Bebas Neue", "Impact", sans-serif' },
      lora: { label: 'Lora — Elegant Serif', stack: '"Lora", Georgia, serif' },
      system: { label: 'System Sans — Clean', stack: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' }
    };

    const presetPositions = {
      'center': { x: 50, y: 50 },
      'top-left': { x: 14, y: 18 },
      'top-right': { x: 86, y: 18 },
      'bottom-left': { x: 14, y: 84 },
      'bottom-right': { x: 86, y: 84 }
    };

    const clamp = (value, min, max) => Math.min(Math.max(value, min), max);
    const safeParse = key => {
      try {
        return JSON.parse(localStorage.getItem(key) || 'null');
      } catch (_) {
        return null;
      }
    };
    const fontStack = id => (FONT_CHOICES[id] ? FONT_CHOICES[id].stack : FONT_CHOICES[DEFAULTS.font].stack);

    let brandingState = { ...BRANDING_DEFAULTS };
    let appearanceState = { ...DEFAULTS };
    let overlays = [];
    const overlayElements = new Map();
    const overlayControls = new Map();
    let hintDismissed = false;
    let stickers = [];

    try {
      hintDismissed = localStorage.getItem(HINT_KEY) === '1';
    } catch (_) {}
    if ($menuHint && hintDismissed) {
      $menuHint.classList.add('is-hidden');
    }

    const applyAppearance = () => {
      document.body.style.setProperty('--bg', appearanceState.bg || DEFAULTS.bg);
    };

    const syncAppearanceInputs = () => {
      if ($bg) $bg.value = appearanceState.bg;
      if ($fg) $fg.value = appearanceState.fg;
      if ($fontDefault) {
        if (!FONT_CHOICES[appearanceState.font]) {
          appearanceState.font = DEFAULTS.font;
        }
        $fontDefault.value = appearanceState.font;
      }
    };

    const removeLegacyStyle = () => {
      try { localStorage.removeItem(LEGACY_STYLE_KEY); } catch (_) {}
    };

    const loadAppearance = () => {
      appearanceState = { ...DEFAULTS };
      const legacy = safeParse(LEGACY_STYLE_KEY) || {};
      const stored = safeParse(APPEARANCE_KEY) || {};
      const combined = { ...legacy, ...stored };
      if (combined.bg) appearanceState.bg = combined.bg;
      if (combined.fg) appearanceState.fg = combined.fg;
      if (combined.font && FONT_CHOICES[combined.font]) {
        appearanceState.font = combined.font;
      }
      syncAppearanceInputs();
      applyAppearance();
    };

    const saveAppearance = () => {
      try {
        localStorage.setItem(APPEARANCE_KEY, JSON.stringify(appearanceState));
      } catch (_) {}
      removeLegacyStyle();
    };

    const clearAppearance = () => {
      appearanceState = { ...DEFAULTS };
      syncAppearanceInputs();
      applyAppearance();
      try { localStorage.removeItem(APPEARANCE_KEY); } catch (_) {}
      removeLegacyStyle();
    };

    const createOverlayData = (overrides = {}) => {
      let pos = typeof overrides.pos === 'string' ? overrides.pos : 'center';
      if (pos !== 'custom' && !presetPositions[pos]) {
        pos = 'custom';
      }
      let x = typeof overrides.x === 'number' ? overrides.x : (typeof overrides.posX === 'number' ? overrides.posX : (presetPositions[pos] ? presetPositions[pos].x : presetPositions.center.x));
      let y = typeof overrides.y === 'number' ? overrides.y : (typeof overrides.posY === 'number' ? overrides.posY : (presetPositions[pos] ? presetPositions[pos].y : presetPositions.center.y));
      if (pos !== 'custom' && presetPositions[pos]) {
        x = presetPositions[pos].x;
        y = presetPositions[pos].y;
      }
      x = clamp(x, 2, 98);
      y = clamp(y, 2, 98);
      const text = typeof overrides.text === 'string' ? overrides.text : 'Fresh overlay text ✨';
      const color = typeof overrides.color === 'string' && overrides.color ? overrides.color : appearanceState.fg;
      const fontId = FONT_CHOICES[overrides.font] ? overrides.font : (FONT_CHOICES[appearanceState.font] ? appearanceState.font : DEFAULTS.font);
      return {
        id: typeof overrides.id === 'string' ? overrides.id : `ov_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        text,
        color,
        font: fontId,
        pos,
        x,
        y
      };
    };

    const saveOverlays = () => {
      try {
        localStorage.setItem(OVERLAY_KEY, JSON.stringify(overlays));
      } catch (_) {}
    };

    const updateOverlayElement = overlay => {
      const refs = overlayElements.get(overlay.id);
      if (!refs) return;
      const { el, inner } = refs;
      el.style.left = `${overlay.x}%`;
      el.style.top = `${overlay.y}%`;
      el.style.fontFamily = fontStack(overlay.font);
      inner.style.fontFamily = fontStack(overlay.font);
      inner.style.color = overlay.color || '#ffffff';
      inner.textContent = overlay.text || '';
      const controls = overlayControls.get(overlay.id);
      if (controls && controls.posSelect) {
        const target = overlay.pos && overlay.pos !== 'custom' ? overlay.pos : 'custom';
        if (controls.posSelect.value !== target) {
          controls.posSelect.value = target;
        }
      }
    };

    const updateOverlayFromPointer = (clientX, clientY, overlay) => {
      if (!overlayArea) return;
      const rect = overlayArea.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = ((clientX - rect.left) / rect.width) * 100;
      const y = ((clientY - rect.top) / rect.height) * 100;
      overlay.x = clamp(x, 2, 98);
      overlay.y = clamp(y, 2, 98);
      overlay.pos = 'custom';
      updateOverlayElement(overlay);
    };

    const attachOverlayDrag = (el, overlay) => {
      if (!el) return;
      let dragging = false;
      el.addEventListener('pointerdown', event => {
        dragging = true;
        overlay.pos = 'custom';
        try { el.setPointerCapture(event.pointerId); } catch (_) {}
        updateOverlayFromPointer(event.clientX, event.clientY, overlay);
        event.preventDefault();
      });
      const stopDrag = event => {
        if (!dragging) return;
        dragging = false;
        try { el.releasePointerCapture(event.pointerId); } catch (_) {}
        saveOverlays();
      };
      el.addEventListener('pointermove', event => {
        if (!dragging) return;
        updateOverlayFromPointer(event.clientX, event.clientY, overlay);
      });
      el.addEventListener('pointerup', stopDrag);
      el.addEventListener('pointercancel', stopDrag);
    };

    const createOverlayElement = overlay => {
      if (!$overlayLayer) return null;
      const el = document.createElement('div');
      el.className = 'overlay-item';
      el.dataset.id = overlay.id;
      const inner = document.createElement('div');
      inner.className = 'overlay-item__inner';
      el.appendChild(inner);
      $overlayLayer.appendChild(el);
      overlayElements.set(overlay.id, { el, inner });
      attachOverlayDrag(el, overlay);
      updateOverlayElement(overlay);
      return el;
    };

    const renderOverlayElements = () => {
      if (!$overlayLayer) return;
      $overlayLayer.innerHTML = '';
      overlayElements.clear();
      overlays.forEach(overlay => createOverlayElement(overlay));
    };

    const removeOverlay = id => {
      overlays = overlays.filter(item => item.id !== id);
      if (!$overlayList) return;
      renderOverlays();
      saveOverlays();
    };

    const renderOverlayControls = () => {
      if (!$overlayList) return;
      $overlayList.innerHTML = '';
      overlayControls.clear();
      if (!overlays.length) {
        const empty = document.createElement('p');
        empty.textContent = 'No overlays yet. Tap “Add overlay text” to sprinkle some flavor 🥬';
        empty.style.opacity = '0.65';
        empty.style.fontSize = '13px';
        empty.style.margin = '0';
        $overlayList.appendChild(empty);
        return;
      }
      const positionOptions = [
        { value: 'center', label: 'Center' },
        { value: 'top-left', label: 'Top-Left' },
        { value: 'top-right', label: 'Top-Right' },
        { value: 'bottom-left', label: 'Bottom-Left' },
        { value: 'bottom-right', label: 'Bottom-Right' },
        { value: 'custom', label: 'Custom (drag)' }
      ];
      overlays.forEach((overlay, index) => {
        const card = document.createElement('div');
        card.className = 'overlay-card';
        card.dataset.id = overlay.id;

        const header = document.createElement('div');
        header.className = 'overlay-card__header';
        const title = document.createElement('span');
        title.textContent = `Overlay ${index + 1} 🥬`;
        const remove = document.createElement('button');
        remove.type = 'button';
        remove.className = 'overlay-remove';
        remove.textContent = 'Remove';
        remove.addEventListener('click', () => removeOverlay(overlay.id));
        header.appendChild(title);
        header.appendChild(remove);

        const textLabel = document.createElement('label');
        textLabel.textContent = 'Text';
        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.placeholder = 'Add overlay text…';
        textInput.value = overlay.text;
        textInput.addEventListener('input', () => {
          overlay.text = textInput.value;
          updateOverlayElement(overlay);
          saveOverlays();
        });
        textLabel.appendChild(textInput);

        const colorLabel = document.createElement('label');
        colorLabel.textContent = 'Color';
        const colorInput = document.createElement('input');
        colorInput.type = 'color';
        colorInput.value = overlay.color || appearanceState.fg;
        colorInput.addEventListener('input', () => {
          overlay.color = colorInput.value;
          updateOverlayElement(overlay);
          saveOverlays();
        });
        colorLabel.appendChild(colorInput);

        const fontLabel = document.createElement('label');
        fontLabel.textContent = 'Font';
        const fontSelect = document.createElement('select');
        Object.entries(FONT_CHOICES).forEach(([id, meta]) => {
          const option = document.createElement('option');
          option.value = id;
          option.textContent = meta.label;
          fontSelect.appendChild(option);
        });
        fontSelect.value = FONT_CHOICES[overlay.font] ? overlay.font : DEFAULTS.font;
        fontSelect.addEventListener('change', () => {
          overlay.font = FONT_CHOICES[fontSelect.value] ? fontSelect.value : DEFAULTS.font;
          updateOverlayElement(overlay);
          saveOverlays();
        });
        fontLabel.appendChild(fontSelect);

        const posLabel = document.createElement('label');
        posLabel.textContent = 'Position';
        const posSelect = document.createElement('select');
        positionOptions.forEach(option => {
          const opt = document.createElement('option');
          opt.value = option.value;
          opt.textContent = option.label;
          posSelect.appendChild(opt);
        });
        posSelect.value = overlay.pos && overlay.pos !== 'custom' ? overlay.pos : 'custom';
        posSelect.addEventListener('change', () => {
          const value = posSelect.value;
          overlay.pos = value;
          if (value !== 'custom' && presetPositions[value]) {
            overlay.x = presetPositions[value].x;
            overlay.y = presetPositions[value].y;
          }
          updateOverlayElement(overlay);
          saveOverlays();
        });
        posLabel.appendChild(posSelect);

        card.appendChild(header);
        card.appendChild(textLabel);
        card.appendChild(colorLabel);
        card.appendChild(fontLabel);
        card.appendChild(posLabel);

        $overlayList.appendChild(card);
        overlayControls.set(overlay.id, {
          card,
          textInput,
          colorInput,
          fontSelect,
          posSelect
        });
      });
    };

    const renderOverlays = () => {
      renderOverlayElements();
      renderOverlayControls();
    };

    const resetOverlays = () => {
      overlays = [createOverlayData({ text: 'Fresh overlay text ✨', pos: 'center' })];
      renderOverlays();
      saveOverlays();
    };

    const loadOverlays = () => {
      overlays = [];
      const stored = safeParse(OVERLAY_KEY);
      if (Array.isArray(stored) && stored.length) {
        overlays = stored.map(item => createOverlayData({
          ...item,
          x: typeof item.x === 'number' ? item.x : item.posX,
          y: typeof item.y === 'number' ? item.y : item.posY
        }));
      } else {
        const legacy = safeParse(LEGACY_STYLE_KEY) || {};
        if (legacy && (legacy.text || legacy.text === '' || typeof legacy.posX === 'number' || typeof legacy.posY === 'number')) {
          overlays.push(createOverlayData({
            text: legacy.text || '',
            color: legacy.fg || appearanceState.fg,
            pos: legacy.pos || 'center',
            x: typeof legacy.posX === 'number' ? legacy.posX : undefined,
            y: typeof legacy.posY === 'number' ? legacy.posY : undefined
          }));
        }
      }
      if (!overlays.length) {
        overlays.push(createOverlayData({ text: 'Fresh overlay text ✨', pos: 'center' }));
      }
      renderOverlays();
      saveOverlays();
    };

    // ---- Branding ----
    const applyBranding = () => {
      const suffix = (brandingState.suffix || '').trim();
      const showEmoji = Boolean(brandingState.showEmoji);
      const emoji = showEmoji ? '🥬' : '';
      if ($brandSuffixEl) {
        if (suffix) {
          $brandSuffixEl.textContent = showEmoji ? `${suffix} ${emoji}` : suffix;
          $brandSuffixEl.dataset.prefix = ' ';
        } else if (showEmoji) {
          $brandSuffixEl.textContent = emoji;
          $brandSuffixEl.dataset.prefix = ' ';
        } else {
          $brandSuffixEl.textContent = '';
          $brandSuffixEl.dataset.prefix = '';
        }
      }
      if ($headerSuffix && $headerSuffix.value !== brandingState.suffix) {
        $headerSuffix.value = brandingState.suffix;
      }
      if ($showEmoji) {
        $showEmoji.checked = showEmoji;
      }
      if ($menuToggle) {
        const labelParts = ['Toggle setup panel for Lettuce Stream'];
        if (suffix) labelParts.push(suffix);
        if (showEmoji) labelParts.push('🥬');
        $menuToggle.setAttribute('aria-label', labelParts.join(' '));
      }
      const titleSuffix = suffix ? ` ${suffix}` : '';
      const titleEmoji = showEmoji ? ' 🥬' : '';
      document.title = `Lettuce Stream${titleSuffix}${titleEmoji}`;
    };

    const saveBranding = () => {
      try {
        localStorage.setItem(BRANDING_KEY, JSON.stringify(brandingState));
      } catch (_) {}
    };

    const loadBranding = () => {
      brandingState = { ...BRANDING_DEFAULTS };
      try {
        const stored = JSON.parse(localStorage.getItem(BRANDING_KEY) || '{}');
        if (typeof stored.suffix === 'string') brandingState.suffix = stored.suffix;
        if (typeof stored.showEmoji === 'boolean') brandingState.showEmoji = stored.showEmoji;
      } catch (_) {}
      applyBranding();
    };

    if ($headerSuffix) {
      $headerSuffix.addEventListener('input', event => {
        brandingState.suffix = event.target.value;
        applyBranding();
        saveBranding();
      });
    }
    if ($showEmoji) {
      $showEmoji.addEventListener('change', event => {
        brandingState.showEmoji = event.target.checked;
        applyBranding();
        saveBranding();
      });
    }

    // ---- Sticker helpers ----
    const positionStickerEl = (el, sticker) => {
      if (!el || !sticker) return;
      el.style.left = `${sticker.x}%`;
      el.style.top = `${sticker.y}%`;
      if (sticker.width) {
        el.style.width = `${sticker.width}px`;
      }
    };

    const saveStickers = () => {
      try {
        localStorage.setItem(STICKER_KEY, JSON.stringify(stickers));
      } catch (_) {}
    };

    const removeSticker = id => {
      stickers = stickers.filter(item => item.id !== id);
      if ($stickerLayer) {
        const existing = $stickerLayer.querySelector(`.sticker[data-id="${id}"]`);
        if (existing) existing.remove();
      }
      saveStickers();
    };

    const updateStickerPosition = (clientX, clientY, sticker, el) => {
      if (!overlayArea) return;
      const rect = overlayArea.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      const x = clamp(((clientX - rect.left) / rect.width) * 100, 1, 99);
      const y = clamp(((clientY - rect.top) / rect.height) * 100, 1, 99);
      sticker.x = x;
      sticker.y = y;
      positionStickerEl(el, sticker);
      saveStickers();
    };

    const attachStickerDrag = (el, sticker) => {
      if (!el) return;
      let dragging = false;
      el.addEventListener('pointerdown', event => {
        const target = event.target;
        if (target && target.classList && target.classList.contains('sticker-remove')) {
          return;
        }
        dragging = true;
        try { el.setPointerCapture(event.pointerId); } catch (_) {}
        event.preventDefault();
      });
      const stopDrag = event => {
        if (!dragging) return;
        dragging = false;
        try { el.releasePointerCapture(event.pointerId); } catch (_) {}
      };
      el.addEventListener('pointermove', event => {
        if (!dragging) return;
        updateStickerPosition(event.clientX, event.clientY, sticker, el);
      });
      el.addEventListener('pointerup', stopDrag);
      el.addEventListener('pointercancel', stopDrag);
    };

    const stickerBaseWidth = () => {
      if (!overlayArea) return 200;
      const rect = overlayArea.getBoundingClientRect();
      if (!rect.width) return 200;
      return Math.max(120, Math.min(rect.width * 0.22, 280));
    };

    const createStickerElement = sticker => {
      if (!$stickerLayer) return null;
      const el = document.createElement('div');
      el.className = 'sticker';
      el.dataset.id = sticker.id;
      const img = document.createElement('img');
      img.src = sticker.src;
      img.alt = 'Custom sticker';
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'sticker-remove';
      remove.textContent = '×';
      remove.addEventListener('click', event => {
        event.stopPropagation();
        removeSticker(sticker.id);
      });
      el.appendChild(img);
      el.appendChild(remove);
      sticker.width = sticker.width || Math.round(stickerBaseWidth());
      positionStickerEl(el, sticker);
      attachStickerDrag(el, sticker);
      $stickerLayer.appendChild(el);
      return el;
    };

    const renderStickers = () => {
      if (!$stickerLayer) return;
      $stickerLayer.innerHTML = '';
      stickers.forEach(sticker => createStickerElement(sticker));
    };

    const addSticker = src => {
      if (!src) return;
      const sticker = {
        id: `s_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
        src,
        x: 50,
        y: 50,
        width: Math.round(stickerBaseWidth())
      };
      stickers.push(sticker);
      createStickerElement(sticker);
      saveStickers();
    };

    const loadStickers = () => {
      stickers = [];
      try {
        const stored = JSON.parse(localStorage.getItem(STICKER_KEY) || '[]');
        if (Array.isArray(stored)) {
          stickers = stored.filter(item => item && typeof item.src === 'string').map(item => ({
            id: item.id || `s_${Date.now()}_${Math.floor(Math.random() * 1000)}`,
            src: item.src,
            x: typeof item.x === 'number' ? item.x : 50,
            y: typeof item.y === 'number' ? item.y : 50,
            width: typeof item.width === 'number' ? item.width : Math.round(stickerBaseWidth())
          }));
        }
      } catch (_) {}
      renderStickers();
    };

    if ($stickerUpload) {
      $stickerUpload.addEventListener('change', event => {
        const input = event.target;
        if (!input || !input.files || !input.files[0]) return;
        const file = input.files[0];
        const reader = new FileReader();
        reader.addEventListener('load', () => {
          if (typeof reader.result === 'string') {
            addSticker(reader.result);
          }
          $stickerUpload.value = '';
        });
        reader.readAsDataURL(file);
      });
    }

    if ($clearStickers) {
      $clearStickers.addEventListener('click', () => {
        stickers = [];
        if ($stickerLayer) {
          $stickerLayer.innerHTML = '';
        }
        saveStickers();
      });
    }

    // ---- Frame layout helpers ----
    let frameTouched = false;

    function clampFrameWithinMain() {
      if (!$frame || !$main) return;
      const mainRect = $main.getBoundingClientRect();
      const frameRect = $frame.getBoundingClientRect();
      if (!mainRect.width || !mainRect.height) return;
      let left = frameRect.left;
      let top = frameRect.top;
      let width = frameRect.width;
      let height = frameRect.height;
      const minWidth = 240;
      const minHeight = 160;
      if (width < minWidth) width = minWidth;
      if (height < minHeight) height = minHeight;
      left = Math.max(mainRect.left + 12, Math.min(left, mainRect.right - width - 12));
      top = Math.max(mainRect.top + 12, Math.min(top, mainRect.bottom - height - 12));
      $frame.style.width = `${width}px`;
      $frame.style.height = `${height}px`;
      $frame.style.left = `${left - mainRect.left}px`;
      $frame.style.top = `${top - mainRect.top}px`;
    }

    function positionFrameInitially() {
      if (!$frame || !$main) return;
      const mainRect = $main.getBoundingClientRect();
      if (!mainRect.width || !mainRect.height) return;
      const collapsed = document.body.classList.contains('panel-collapsed');
      const factor = collapsed ? 0.9 : 0.75;
      const maxWidth = collapsed ? 1400 : 1100;
      const maxHeightBase = collapsed ? 0.82 : 0.7;
      const baseWidth = Math.min(mainRect.width * factor, maxWidth);
      const baseHeight = Math.min(mainRect.height * maxHeightBase, collapsed ? 720 : 660);
      const finalWidth = Math.max(baseWidth, 320);
      const finalHeight = Math.max(baseHeight, 200);
      $frame.style.width = `${finalWidth}px`;
      $frame.style.height = `${finalHeight}px`;
      $frame.style.left = `${Math.max(12, (mainRect.width - finalWidth) / 2)}px`;
      $frame.style.top = `${Math.max(24, (mainRect.height - finalHeight) / 2)}px`;
      frameTouched = false;
    }

    // ---- Appearance controls ----
    if ($bg) {
      $bg.addEventListener('input', () => {
        appearanceState.bg = $bg.value;
        applyAppearance();
        saveAppearance();
      });
    }

    if ($fg) {
      $fg.addEventListener('input', () => {
        const previous = appearanceState.fg;
        appearanceState.fg = $fg.value;
        overlays.forEach(overlay => {
          if (overlay.color === previous) {
            overlay.color = appearanceState.fg;
            updateOverlayElement(overlay);
            const refs = overlayControls.get(overlay.id);
            if (refs && refs.colorInput && refs.colorInput.value !== overlay.color) {
              refs.colorInput.value = overlay.color;
            }
          }
        });
        saveOverlays();
        saveAppearance();
      });
    }

    if ($fontDefault) {
      $fontDefault.addEventListener('change', () => {
        const previous = appearanceState.font;
        const chosen = FONT_CHOICES[$fontDefault.value] ? $fontDefault.value : DEFAULTS.font;
        appearanceState.font = chosen;
        overlays.forEach(overlay => {
          if (overlay.font === previous) {
            overlay.font = appearanceState.font;
            updateOverlayElement(overlay);
            const refs = overlayControls.get(overlay.id);
            if (refs && refs.fontSelect && refs.fontSelect.value !== overlay.font) {
              refs.fontSelect.value = overlay.font;
            }
          }
        });
        saveOverlays();
        saveAppearance();
      });
    }

    if ($addOverlay) {
      $addOverlay.addEventListener('click', () => {
        const defaultText = overlays.length ? 'New overlay text' : 'Fresh overlay text ✨';
        overlays.push(createOverlayData({ text: defaultText, pos: 'center' }));
        renderOverlays();
        saveOverlays();
      });
    }

    const saveCurrentStyle = () => {
      saveAppearance();
      saveOverlays();
      setPanelCollapsed(true);
    };

    const handleClearStyle = () => {
      clearAppearance();
      resetOverlays();
    };

    const saveButton = $('#saveStyle');
    if (saveButton) {
      saveButton.addEventListener('click', saveCurrentStyle);
    }

    const clearButton = $('#clearStyle');
    if (clearButton) {
      clearButton.addEventListener('click', handleClearStyle);
    }

    // ---- Fullscreen control ----
    const updateFullscreenState = () => {
      if (!$stage || !$expand) return;
      const fullscreenEl = document.fullscreenElement || document.webkitFullscreenElement;
      const isFullscreen = fullscreenEl === $stage;
      $stage.classList.toggle('fullscreen-active', isFullscreen);
      if ($frame) {
        $frame.classList.toggle('fullscreen-mode', isFullscreen);
      }
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

    // ---- Panel visibility ----
    const setPanelCollapsed = (collapsed, options = {}) => {
      const { fromUser = false } = options;
      if (!$rtspPanel) return;
      $rtspPanel.classList.toggle('collapsed', collapsed);
      document.body.classList.toggle('panel-collapsed', collapsed);
      if ($menuToggle) {
        $menuToggle.setAttribute('aria-expanded', String(!collapsed));
      }
      if ($menuHint) {
        if (collapsed && fromUser && !hintDismissed) {
          hintDismissed = true;
          $menuHint.classList.add('is-hidden');
          try { localStorage.setItem(HINT_KEY, '1'); } catch (_) {}
        } else if (!hintDismissed) {
          $menuHint.classList.remove('is-hidden');
        }
      }
      if ($frame && $main && !frameTouched) {
        const mainRect = $main.getBoundingClientRect();
        const ratio = $frame.offsetHeight / Math.max($frame.offsetWidth, 1);
        const targetFactor = collapsed ? 0.9 : 0.75;
        const maxWidth = collapsed ? 1400 : 1100;
        let width = Math.max(320, Math.min(mainRect.width * targetFactor, maxWidth));
        let height = Math.max(200, width * (ratio || 0.5625));
        const maxHeight = Math.max(240, mainRect.height - 48);
        if (height > maxHeight) {
          height = maxHeight;
          width = Math.max(320, height / (ratio || 0.5625));
        }
        $frame.style.width = `${width}px`;
        $frame.style.height = `${height}px`;
        $frame.style.left = `${Math.max(12, (mainRect.width - width) / 2)}px`;
        $frame.style.top = `${Math.max(24, (mainRect.height - height) / 2)}px`;
      }
      setTimeout(() => clampFrameWithinMain(), 50);
    };

    if ($menuToggle) {
      $menuToggle.addEventListener('click', () => {
        const collapsed = document.body.classList.contains('panel-collapsed');
        setPanelCollapsed(!collapsed, { fromUser: true });
        if (!document.body.classList.contains('panel-collapsed') && $u && typeof $u.focus === 'function') {
          setTimeout(() => {
            try {
              $u.focus({ preventScroll: true });
            } catch (_) {
              $u.focus();
            }
          }, 120);
        }
      });
    }

    // ---- Frame dragging ----
    if ($frameHandle && $frame) {
      let draggingFrame = false;
      let startX = 0, startY = 0, frameStartLeft = 0, frameStartTop = 0;
      $frameHandle.addEventListener('pointerdown', event => {
        if (!$main) return;
        draggingFrame = true;
        startX = event.clientX;
        startY = event.clientY;
        const rect = $frame.getBoundingClientRect();
        const mainRect = $main.getBoundingClientRect();
        frameStartLeft = rect.left - mainRect.left;
        frameStartTop = rect.top - mainRect.top;
        try { $frameHandle.setPointerCapture(event.pointerId); } catch (_) {}
        event.preventDefault();
      });
      const stopDragging = event => {
        if (!draggingFrame) return;
        draggingFrame = false;
        try { $frameHandle.releasePointerCapture(event.pointerId); } catch (_) {}
        clampFrameWithinMain();
      };
      $frameHandle.addEventListener('pointermove', event => {
        if (!draggingFrame) return;
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;
        $frame.style.left = `${frameStartLeft + deltaX}px`;
        $frame.style.top = `${frameStartTop + deltaY}px`;
        frameTouched = true;
      });
      $frameHandle.addEventListener('pointerup', stopDragging);
      $frameHandle.addEventListener('pointercancel', stopDragging);
    }

    if ($frameResizer && $frame) {
      let resizing = false;
      let startX = 0, startY = 0, startWidth = 0, startHeight = 0;
      $frameResizer.addEventListener('pointerdown', event => {
        resizing = true;
        startX = event.clientX;
        startY = event.clientY;
        const rect = $frame.getBoundingClientRect();
        startWidth = rect.width;
        startHeight = rect.height;
        try { $frameResizer.setPointerCapture(event.pointerId); } catch (_) {}
        event.preventDefault();
      });
      const stopResizing = event => {
        if (!resizing) return;
        resizing = false;
        try { $frameResizer.releasePointerCapture(event.pointerId); } catch (_) {}
        clampFrameWithinMain();
      };
      $frameResizer.addEventListener('pointermove', event => {
        if (!resizing) return;
        const deltaX = event.clientX - startX;
        const deltaY = event.clientY - startY;
        const minWidth = 240;
        const minHeight = 160;
        const newWidth = Math.max(minWidth, startWidth + deltaX);
        const newHeight = Math.max(minHeight, startHeight + deltaY);
        $frame.style.width = `${newWidth}px`;
        $frame.style.height = `${newHeight}px`;
        frameTouched = true;
      });
      $frameResizer.addEventListener('pointerup', stopResizing);
      $frameResizer.addEventListener('pointercancel', stopResizing);
    }

    window.addEventListener('resize', () => {
      clampFrameWithinMain();
    });

    // ---- RTSP state ----
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

    // Init
    loadBranding();
    loadStickers();
    loadAppearance();
    loadOverlays();
    updateFullscreenState();
    loadRtsp();
    positionFrameInitially();
    clampFrameWithinMain();
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
