"""
Facemash-style app: head-to-head voting with strict duplicate prevention, 
URL-encoded image paths, recursive loading, session-based round redirects, 
shared global win/loss counting, and password-protected admin reset.

Setup:
    pip install flask gunicorn
    mkdir static/images
    # Place your image files inside static/images/ (supports subfolders too!)
    python facemash.py

Data is stored in scores.json (created automatically).
"""

import json
import random
import os
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request, redirect, url_for

app = Flask(__name__)

# --- CONFIGURATION ---
ADMIN_PASSWORD = "brolx"  # Admin password for resetting scores

IMAGE_DIR = Path("static/images")
SCORES_FILE = Path("scores.json")
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".jfif", ".heic", ".heif", ".gif", ".avif", ".bmp"}


def load_scores():
    """Load existing vote counts, supporting recursive subfolders inside static/images."""
    images = sorted(
        str(f.relative_to(IMAGE_DIR)).replace("\\", "/")
        for f in IMAGE_DIR.glob("**/*")
        if f.is_file() and f.suffix.lower() in VALID_EXTENSIONS
    )
    if not images:
        raise RuntimeError(
            f"No images found in {IMAGE_DIR}/ — place your image files there."
        )

    scores = {}
    if SCORES_FILE.exists():
        scores = json.loads(SCORES_FILE.read_text())

    for name in images:
        scores.setdefault(name, {"wins": 0, "losses": 0})

    # Drop entries for images that no longer exist on disk
    scores = {k: v for k, v in scores.items() if k in images}
    save_scores(scores)
    return scores


def save_scores(scores):
    SCORES_FILE.write_text(json.dumps(scores, indent=2))


def record_vote(scores, winner, loser):
    scores[winner]["wins"] += 1
    scores[loser]["losses"] += 1
    save_scores(scores)


PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FACEMASH</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin:0; font-family: 'Segoe UI', system-ui, sans-serif;
      background: radial-gradient(circle at top, #1b1030 0%, #0a0612 60%, #050308 100%);
      color:#f5f5f7; text-align:center; min-height:100vh; padding:1.5rem 1rem 3rem;
    }
    .brand {
      font-size: clamp(2.2rem, 9vw, 3.2rem); font-weight:900; letter-spacing:0.06em;
      margin: 0.5rem 0 0.2rem; background: linear-gradient(90deg,#ff4d8d,#ff9d4d,#ffd93d);
      -webkit-background-clip:text; background-clip:text; color:transparent;
      text-transform:uppercase;
    }
    .tagline {
      font-size: clamp(1rem, 4vw, 1.4rem); font-weight:600; color:#ddd;
      margin: 0 0 1.2rem; letter-spacing:0.02em;
    }
    .arena {
      display:flex; justify-content:center; align-items:stretch; gap:1.5rem;
      margin-top:1rem; flex-wrap:wrap; max-width:960px; margin-left:auto; margin-right:auto;
      transition: opacity 0.15s ease;
    }
    .arena.loading {
      pointer-events: none;
      opacity: 0.5;
    }
    .card {
      cursor:pointer; border-radius:18px; overflow:hidden; position:relative;
      flex:1 1 340px; max-width:440px; min-width:200px;
      border:2px solid rgba(255,255,255,0.08);
      box-shadow: 0 8px 24px rgba(0,0,0,0.4);
      transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
      background:#151022;
    }
    .card:hover, .card:active {
      transform: translateY(-4px) scale(1.02);
      border-color:#ff4d8d;
      box-shadow: 0 12px 30px rgba(255,77,141,0.35);
    }
    .card img {
      width:100%; aspect-ratio: 1 / 1; object-fit:cover; display:block;
    }
    .vs {
      display:flex; align-items:center; justify-content:center;
      font-weight:900; font-size:1.5rem; color:#ff9d4d; min-width:2.5rem;
    }
    #status { margin-top:1.3rem; font-size:1.1rem; color:#ffd93d; min-height:1.2rem; font-weight:700; }
    .nav-links {
      margin-top: 1.6rem;
      display: flex;
      justify-content: center;
      gap: 2rem;
      align-items: center;
    }
    a.link {
      color:#ffd93d; text-decoration:none;
      font-weight:600; border-bottom:1px solid rgba(255,217,61,0.4); padding-bottom:2px;
    }
    a.reset-link {
      color:#ff4d8d; text-decoration:none;
      font-weight:600; border-bottom:1px solid rgba(255,77,141,0.4); padding-bottom:2px;
      cursor: pointer;
    }
    @media (max-width: 480px) {
      .arena { gap:0.7rem; }
      .vs { min-width:1.2rem; font-size:1rem; }
    }
  </style>
</head>
<body>
  <div class="brand">Facemash</div>
  <div class="tagline">Who is the hottest?</div>
  <div class="arena" id="arena"></div>
  <div id="status"></div>
  <div class="nav-links">
    <a class="link" href="/leaderboard">🏆 View Leaderboard</a>
    <a class="reset-link" onclick="triggerReset()">⚙️ Admin Reset</a>
  </div>

<script>
let totalImages = 0;
let currentPair = [];

function renderPair(pair) {
  currentPair = pair;
  const arena = document.getElementById('arena');
  arena.classList.remove('loading');
  arena.innerHTML = '';
  if (!pair || pair.length < 2) {
    arena.innerHTML = '<p>Not enough images in the folder yet.</p>';
    return;
  }
  
  const leftImg = pair[0].split('/').map(encodeURIComponent).join('/');
  const rightImg = pair[1].split('/').map(encodeURIComponent).join('/');

  const left = document.createElement('div');
  left.className = 'card';
  left.innerHTML = `<img src="/static/images/${leftImg}">`;
  left.onclick = () => vote(pair[0], pair[1]);

  const vs = document.createElement('div');
  vs.className = 'vs';
  vs.textContent = 'VS';

  const right = document.createElement('div');
  right.className = 'card';
  right.innerHTML = `<img src="/static/images/${rightImg}">`;
  right.onclick = () => vote(pair[1], pair[0]);

  arena.appendChild(left);
  arena.appendChild(vs);
  arena.appendChild(right);
}

async function loadPair() {
  const res = await fetch('/api/pair');
  const data = await res.json();
  totalImages = data.total_images || 0;
  renderPair(data.pair);
}

async function vote(winner, loser) {
  const arena = document.getElementById('arena');
  arena.classList.add('loading');
  document.getElementById('status').innerText = 'Recording vote...';
  
  await fetch('/api/vote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({winner, loser})
  });

  // Track session vote count for auto-redirect per round
  let sessionVotes = parseInt(sessionStorage.getItem('sessionVotes') || '0') + 1;
  sessionStorage.setItem('sessionVotes', sessionVotes);

  // Trigger redirect once user completes a round equal to the number of images
  if (totalImages > 0 && sessionVotes >= totalImages) {
    sessionStorage.setItem('sessionVotes', '0');
    document.getElementById('status').innerText = '🎉 Round complete! Redirecting to Leaderboard...';
    setTimeout(() => {
      window.location.href = '/leaderboard';
    }, 1000);
    return;
  }

  document.getElementById('status').innerText = '';

  // Pass current active pair to exclude them from the next opponent selection
  const excludeQuery = `?winner=${encodeURIComponent(winner)}&loser=${encodeURIComponent(loser)}`;
  const oppRes = await fetch('/api/opponent' + excludeQuery);
  const oppData = await oppRes.json();
  
  if (oppData.opponent) {
    const nextPair = Math.random() < 0.5 ? [winner, oppData.opponent] : [oppData.opponent, winner];
    renderPair(nextPair);
  } else {
    loadPair();
  }
}

function triggerReset() {
  const pwd = prompt("Enter Admin Password to Reset Scores:");
  if (pwd) {
    window.location.href = "/admin-reset-secret?pwd=" + encodeURIComponent(pwd);
  }
}

loadPair();
</script>
</body>
</html>
"""

LEADERBOARD_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FACEMASH Leaderboard</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin:0; font-family: 'Segoe UI', system-ui, sans-serif;
      background: radial-gradient(circle at top, #1b1030 0%, #0a0612 55%, #050308 100%);
      color:#f5f5f7; text-align:center; min-height:100vh; padding:1.5rem 1rem 3rem;
    }
    .brand {
      font-size: clamp(1.8rem, 7vw, 2.6rem); font-weight:900; letter-spacing:0.06em;
      margin: 0.5rem 0 0.1rem; background: linear-gradient(90deg,#ff4d8d,#ff9d4d,#ffd93d);
      -webkit-background-clip:text; background-clip:text; color:transparent;
      text-transform:uppercase;
    }
    .subhead {
      font-size:1rem; font-weight:600; color:#bbb; margin-bottom:2rem;
      letter-spacing:0.15em; text-transform:uppercase;
    }

    /* ---- Podium ---- */
    .podium {
      display:flex; justify-content:center; align-items:flex-end;
      gap: 0.8rem; max-width:640px; margin: 0 auto 2.5rem;
    }
    .pod {
      flex:1; display:flex; flex-direction:column; align-items:center;
      animation: rise 0.6s ease both;
    }
    .pod.p1 { order:2; }
    .pod.p2 { order:1; }
    .pod.p3 { order:3; }
    @keyframes rise {
      from {
