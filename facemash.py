"""
Facemash-style app: head-to-head image voting with Elo-based ranking.

Setup:
    pip install flask
    mkdir static/images
    # Place your image files (.jpg, .jpeg, .png, .webp) inside static/images/
    python facemash.py
    # Open http://127.0.0.1:5000

Data is stored in scores.json (created automatically).
"""

import json
import random
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

IMAGE_DIR = Path("static/images")
SCORES_FILE = Path("scores.json")
K_FACTOR = 32          # Elo sensitivity
STARTING_ELO = 1200
VALID_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def load_scores():
    """Load existing Elo scores, or initialize new ones from images on disk."""
    images = sorted(
        f.name for f in IMAGE_DIR.glob("*")
        if f.suffix.lower() in VALID_EXTENSIONS
    )
    if not images:
        raise RuntimeError(
            f"No images found in {IMAGE_DIR}/ — place your image files (jpg, png, webp) there."
        )

    scores = {}
    if SCORES_FILE.exists():
        scores = json.loads(SCORES_FILE.read_text())

    for name in images:
        scores.setdefault(name, {"elo": STARTING_ELO, "wins": 0, "losses": 0})

    # Drop entries for images that no longer exist on disk
    scores = {k: v for k, v in scores.items() if k in images}
    save_scores(scores)
    return scores


def save_scores(scores):
    SCORES_FILE.write_text(json.dumps(scores, indent=2))


def expected_score(rating_a, rating_b):
    return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))


def update_elo(scores, winner, loser):
    r_w, r_l = scores[winner]["elo"], scores[loser]["elo"]
    e_w = expected_score(r_w, r_l)
    e_l = expected_score(r_l, r_w)
    scores[winner]["elo"] = round(r_w + K_FACTOR * (1 - e_w), 1)
    scores[loser]["elo"] = round(r_l + K_FACTOR * (0 - e_l), 1)
    scores[winner]["wins"] += 1
    scores[loser]["losses"] += 1
    save_scores(scores)


PAGE_TEMPLATE = """
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>FACEMASH</title>
  <style>
    :root {
      --bg1:#1b1030; --bg2:#0a0612; --bg3:#050308;
      --pink:#ff4d8d; --orange:#ff9d4d; --gold:#ffd93d;
      padding-top: env(safe-area-inset-top, 0px);
      padding-bottom: env(safe-area-inset-bottom, 0px);
    }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    html, body { height:100%; }
    body {
      margin:0; font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
      background: radial-gradient(circle at 50% 0%, var(--bg1) 0%, var(--bg2) 55%, var(--bg3) 100%);
      background-attachment: fixed;
      color:#f5f5f7; text-align:center;
      padding: calc(1.6rem + env(safe-area-inset-top, 0px)) 1rem calc(2.5rem + env(safe-area-inset-bottom, 0px));
      overflow-x:hidden;
    }
    .glow {
      position:fixed; top:-120px; left:50%; transform:translateX(-50%);
      width:360px; height:360px; border-radius:50%;
      background: radial-gradient(circle, rgba(255,77,141,0.25), transparent 70%);
      filter: blur(10px); pointer-events:none; z-index:0;
    }
    .wrap { position:relative; z-index:1; }
    .brand {
      font-size: clamp(2.1rem, 9vw, 3.2rem); font-weight:900; letter-spacing:0.05em;
      margin: 0.2rem 0 0.15rem; background: linear-gradient(90deg,var(--pink),var(--orange),var(--gold));
      -webkit-background-clip:text; background-clip:text; color:transparent;
      text-transform:uppercase; text-shadow: 0 0 40px rgba(255,77,141,0.25);
    }
    .tagline {
      font-size: clamp(0.95rem, 4vw, 1.3rem); font-weight:600; color:#ddd;
      margin: 0 0 0.4rem; letter-spacing:0.02em;
    }
    .vote-count {
      font-size:0.78rem; color:#888; margin-bottom:1.4rem; letter-spacing:0.04em;
    }
    .vote-count b { color:var(--gold); font-weight:700; }

    .arena {
      display:flex; justify-content:center; align-items:stretch; gap:1rem;
      margin-top:0.5rem; flex-wrap:wrap; max-width:760px; margin-left:auto; margin-right:auto;
      transition: opacity 0.18s ease;
    }
    .arena.fading { opacity:0.35; }

    .card {
      cursor:pointer; border-radius:20px; overflow:hidden; position:relative;
      flex:1 1 260px; max-width:340px; min-width:140px;
      border:1px solid rgba(255,255,255,0.1);
      box-shadow: 0 10px 30px rgba(0,0,0,0.45);
      transition: transform 0.18s cubic-bezier(.2,.8,.2,1), border-color 0.18s ease, box-shadow 0.18s ease;
      background: linear-gradient(160deg, rgba(255,255,255,0.06), rgba(255,255,255,0.01));
      backdrop-filter: blur(6px);
      -webkit-user-select:none; user-select:none;
    }
    .card:hover { transform: translateY(-5px) scale(1.02); border-color:var(--pink); box-shadow: 0 16px 36px rgba(255,77,141,0.3); }
    .card:active { transform: scale(0.97); border-color:var(--gold); }
    .card img {
      width:100%; aspect-ratio: 1 / 1; object-fit:cover; display:block;
      pointer-events:none;
    }
    .card .glint {
      position:absolute; inset:0; background: linear-gradient(180deg, transparent 60%, rgba(0,0,0,0.45) 100%);
      pointer-events:none;
    }
    .card .pick-badge {
      position:absolute; top:10px; right:10px; background:rgba(0,0,0,0.5);
      border:1px solid rgba(255,255,255,0.25); color:#fff; font-size:0.68rem;
      font-weight:700; letter-spacing:0.05em; padding:0.3rem 0.6rem; border-radius:999px;
      backdrop-filter: blur(4px); text-transform:uppercase;
    }

    .vs {
      display:flex; align-items:center; justify-content:center;
      font-weight:900; font-size:1.1rem; color:var(--orange); min-width:2.2rem;
      text-shadow: 0 0 16px rgba(255,157,77,0.5);
    }

    #status {
      margin-top:1.1rem; font-size:0.85rem; color:#999; min-height:1.2rem;
      transition: opacity 0.15s ease;
    }
    a.link {
      display:inline-block; margin-top:1.6rem; color:var(--gold); text-decoration:none;
      font-weight:700; font-size:0.95rem;
      border:1px solid rgba(255,217,61,0.35); padding:0.55rem 1.3rem; border-radius:999px;
      background:rgba(255,217,61,0.06); transition:0.15s ease;
    }
    a.link:active { transform:scale(0.96); background:rgba(255,217,61,0.14); }

    @media (max-width: 480px) {
      .arena { gap:0.6rem; }
      .vs { min-width:1.3rem; font-size:0.95rem; }
      .card { max-width:46vw; }
    }
  </style>
</head>
<body>
  <div class="glow"></div>
  <div class="wrap">
    <div class="brand">Facemash</div>
    <div class="tagline">Who is the winner?</div>
    <div class="vote-count" id="voteCount"></div>
    <div class="arena" id="arena"></div>
    <div id="status"></div>
    <p><a class="link" href="/leaderboard">🏆 View Leaderboard</a></p>
  </div>

<script>
let voteTally = 0;

function renderPair(pair) {
  const arena = document.getElementById('arena');
  arena.classList.remove('fading');
  arena.innerHTML = '';
  if (!pair || pair.length < 2) {
    arena.innerHTML = '<p>Not enough images in the folder yet.</p>';
    return;
  }

  const makeCard = (img, other) => {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<img src="/static/images/${img}"><div class="glint"></div><div class="pick-badge">Tap to pick</div>`;
    div.onclick = () => vote(img, other);
    return div;
  };

  const vs = document.createElement('div');
  vs.className = 'vs';
  vs.textContent = 'VS';

  arena.appendChild(makeCard(pair[0], pair[1]));
  arena.appendChild(vs);
  arena.appendChild(makeCard(pair[1], pair[0]));
}

async function loadPair() {
  const res = await fetch('/api/pair');
  const data = await res.json();
  renderPair(data.pair);
}

async function vote(winner, loser) {
  document.getElementById('arena').classList.add('fading');
  document.getElementById('status').innerText = 'Recording vote...';

  await fetch('/api/vote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({winner, loser})
  });

  voteTally++;
  document.getElementById('voteCount').innerHTML = 'Votes cast this session: <b>' + voteTally + '</b>';
  document.getElementById('status').innerText = '';

  const res = await fetch('/api/opponent?exclude=' + encodeURIComponent(winner));
  const data = await res.json();
  if (data.opponent) {
    renderPair([winner, data.opponent]);
  } else {
    loadPair();
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
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <title>FACEMASH Leaderboard</title>
  <style>
    :root {
      --bg1:#1b1030; --bg2:#0a0612; --bg3:#050308;
      --pink:#ff4d8d; --orange:#ff9d4d; --gold:#ffd93d;
    }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    body {
      margin:0; font-family: -apple-system, 'Segoe UI', system-ui, sans-serif;
      background: radial-gradient(circle at 50% 0%, var(--bg1) 0%, var(--bg2) 55%, var(--bg3) 100%);
      background-attachment: fixed;
      color:#f5f5f7; text-align:center; min-height:100vh;
      padding: calc(1.6rem + env(safe-area-inset-top, 0px)) 1rem calc(2.5rem + env(safe-area-inset-bottom, 0px));
    }
    .brand {
      font-size: clamp(1.7rem, 7vw, 2.5rem); font-weight:900; letter-spacing:0.05em;
      margin: 0.2rem 0 0.1rem; background: linear-gradient(90deg,var(--pink),var(--orange),var(--gold));
      -webkit-background-clip:text; background-clip:text; color:transparent;
      text-transform:uppercase;
    }
    .subhead {
      font-size:0.85rem; font-weight:700; color:#999; margin-bottom:2rem;
      letter-spacing:0.18em; text-transform:uppercase;
    }

    .podium {
      display:flex; justify-content:center; align-items:flex-end;
      gap: 0.7rem; max-width:640px; margin: 0 auto 2.5rem;
    }
    .pod {
      flex:1; display:flex; flex-direction:column; align-items:center;
      animation: rise 0.55s cubic-bezier(.2,.8,.2,1) both;
    }
    .pod.p1 { order:2; } .pod.p2 { order:1; } .pod.p3 { order:3; }
    .pod.p2 { animation-delay: 0.05s; } .pod.p3 { animation-delay: 0.1s; }
    @keyframes rise { from { opacity:0; transform: translateY(26px); } to { opacity:1; transform: translateY(0); } }

    .pod .medal { font-size:1.5rem; margin-bottom:0.25rem; filter: drop-shadow(0 2px 6px rgba(0,0,0,0.5)); }
    .pod .avatar-wrap { border-radius:50%; padding:3px; }
    .pod.p1 .avatar-wrap { background: linear-gradient(135deg,var(--gold),var(--orange)); box-shadow:0 0 24px rgba(255,217,61,0.35); }
    .pod.p2 .avatar-wrap { background: linear-gradient(135deg,#d8d8e0,#9a9aa8); }
    .pod.p3 .avatar-wrap { background: linear-gradient(135deg,#e0a370,#a5673a); }
    .pod img { display:block; border-radius:50%; object-fit:cover; background:#151022; border:3px solid #0a0612; }
    .pod.p1 img { width:100px; height:100px; }
    .pod.p2 img, .pod.p3 img { width:76px; height:76px; }
    .pod .pname {
      margin-top:0.55rem; font-size:0.8rem; font-weight:600; max-width:108px;
      overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    }
    .pod .pelo { font-size:0.76rem; color:var(--orange); font-weight:700; margin-top:0.1rem; }
    .pod .stand {
      margin-top:0.65rem; width:100%; border-radius:10px 10px 0 0;
      display:flex; align-items:flex-start; justify-content:center;
      font-weight:900; color:rgba(255,255,255,0.85); padding-top:0.4rem;
    }
    .pod.p1 .stand { height:72px; background:linear-gradient(180deg,#ffd93d38,#ffd93d08); font-size:1.3rem; }
    .pod.p2 .stand { height:50px; background:linear-gradient(180deg,#d8d8e038,#d8d8e008); font-size:1.1rem; }
    .pod.p3 .stand { height:36px; background:linear-gradient(180deg,#e0a37038,#e0a37008); font-size:1.1rem; }

    .board { max-width:520px; margin:0 auto; }
    .board-title {
      text-align:left; font-size:0.74rem; letter-spacing:0.12em; text-transform:uppercase;
      color:#777; margin:0 0 0.6rem 0.4rem; font-weight:700;
    }
    .row {
      display:flex; align-items:center; gap:0.75rem; padding:0.6rem 0.65rem;
      text-align:left; border-radius:14px; background:rgba(255,255,255,0.025);
      margin-bottom:0.4rem; border:1px solid rgba(255,255,255,0.05);
      transition: background 0.15s ease, transform 0.15s ease;
    }
    .row:active { transform: scale(0.985); background:rgba(255,255,255,0.05); }
    .rank { width:1.7rem; font-weight:800; color:#777; flex-shrink:0; font-size:0.85rem; }
    .row img {
      width:42px; height:42px; object-fit:cover; border-radius:10px; flex-shrink:0;
      border:1px solid rgba(255,255,255,0.08);
    }
    .name { flex:1; font-size:0.84rem; word-break:break-word; }
    .stats { font-size:0.74rem; color:#999; white-space:nowrap; text-align:right; }
    .elo { font-weight:800; color:var(--orange); display:block; font-size:0.82rem; }
    .wl { color:#777; }

    a.link {
      display:inline-block; margin-top:2rem; color:var(--gold); text-decoration:none;
      font-weight:700; font-size:0.9rem;
      border:1px solid rgba(255,217,61,0.35); padding:0.5rem 1.2rem; border-radius:999px;
      background:rgba(255,217,61,0.06);
    }
    a.link:active { transform:scale(0.96); }

    @media (max-width:420px) {
      .podium { gap:0.35rem; }
      .pod.p1 img { width:80px; height:80px; }
      .pod.p2 img, .pod.p3 img { width:60px; height:60px; }
      .pod .pname { max-width:76px; font-size:0.7rem; }
    }
  </style>
</head>
<body>
  <div class="brand">Facemash</div>
  <div class="subhead">Leaderboard</div>

  {% if ranked|length >= 1 %}
  <div class="podium">
    {% if ranked|length >= 2 %}
    {% set n2, s2 = ranked[1] %}
    <div class="pod p2">
      <div class="medal">🥈</div>
      <div class="avatar-wrap"><img src="/static/images/{{ n2 }}"></div>
      <div class="pname">{{ n2 }}</div>
      <div class="pelo">{{ s2.elo }}</div>
      <div class="stand">2</div>
    </div>
    {% endif %}

    {% set n1, s1 = ranked[0] %}
    <div class="pod p1">
      <div class="medal">🥇</div>
      <div class="avatar-wrap"><img src="/static/images/{{ n1 }}"></div>
      <div class="pname">{{ n1 }}</div>
      <div class="pelo">{{ s1.elo }}</div>
      <div class="stand">1</div>
    </div>

    {% if ranked|length >= 3 %}
    {% set n3, s3 = ranked[2] %}
    <div class="pod p3">
      <div class="medal">🥉</div>
      <div class="avatar-wrap"><img src="/static/images/{{ n3 }}"></div>
      <div class="pname">{{ n3 }}</div>
      <div class="pelo">{{ s3.elo }}</div>
      <div class="stand">3</div>
    </div>
    {% endif %}
  </div>
  {% endif %}

  <div class="board">
    {% if ranked|length > 3 %}<div class="board-title">Full Rankings</div>{% endif %}
    {% for name, s in ranked %}
    <div class="row">
      <div class="rank">#{{ loop.index }}</div>
      <img src="/static/images/{{ name }}">
      <div class="name">{{ name }}</div>
      <div class="stats">
        <span class="elo">{{ s.elo }}</span>
        <span class="wl">{{ s.wins }}W / {{ s.losses }}L</span>
      </div>
    </div>
    {% endfor %}
  </div>
  <p><a class="link" href="/">⬅ Back to voting</a></p>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(PAGE_TEMPLATE)


@app.route("/api/pair")
def api_pair():
    scores = load_scores()
    names = list(scores.keys())
    if len(names) < 2:
        return jsonify({"pair": []})
    pair = random.sample(names, 2)
    return jsonify({"pair": pair})


@app.route("/api/opponent")
def api_opponent():
    scores = load_scores()
    exclude = request.args.get("exclude", "")
    candidates = [n for n in scores.keys() if n != exclude]
    if not candidates:
        return jsonify({"opponent": None})
    return jsonify({"opponent": random.choice(candidates)})


@app.route("/api/vote", methods=["POST"])
def api_vote():
    scores = load_scores()
    data = request.get_json()
    winner, loser = data["winner"], data["loser"]
    if winner not in scores or loser not in scores:
        return jsonify({"error": "Unknown image."}), 400
    update_elo(scores, winner, loser)
    return jsonify({"ok": True})


@app.route("/leaderboard")
def leaderboard():
    scores = load_scores()
    ranked = sorted(scores.items(), key=lambda kv: kv[1]["elo"], reverse=True)
    return render_template_string(LEADERBOARD_TEMPLATE, ranked=ranked)


if __name__ == "__main__":
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True)
