"""
Facemash-style app: head-to-head image voting with Elo-based ranking,
split into two separate pools so images never get compared across groups.

Setup:
    pip install flask
    mkdir static/images
    # name your files with a prefix so the app knows which pool they belong to:
    #   m_yourname.jpg   -> "M" pool
    #   f_yourname.jpg   -> "F" pool
    # (any file without one of these prefixes is ignored)
    python facemash.py
    # open http://127.0.0.1:5000

Data is stored in scores.json (created automatically). Swap in a real
database if you need persistence beyond a single machine / process.
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

CATEGORIES = {
    "m": "Men",
    "f": "Women",
}
PREFIX_MAP = {"m_": "m", "f_": "f"}


def category_of(filename):
    lower = filename.lower()
    for prefix, cat in PREFIX_MAP.items():
        if lower.startswith(prefix):
            return cat
    return None  # unrecognized prefix -> excluded from both pools


def load_scores():
    """Load existing Elo scores, or initialize new ones from images on disk."""
    all_files = sorted(
        f.name for f in IMAGE_DIR.glob("*")
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    images = [f for f in all_files if category_of(f) is not None]
    if not images:
        raise RuntimeError(
            f"No images found in {IMAGE_DIR}/ with an m_ or f_ prefix — "
            "rename your files, e.g. m_photo1.jpg / f_photo1.jpg."
        )

    scores = {}
    if SCORES_FILE.exists():
        scores = json.loads(SCORES_FILE.read_text())

    for name in images:
        scores.setdefault(name, {"elo": STARTING_ELO, "wins": 0, "losses": 0})

    # drop entries for images that no longer exist or lost their prefix
    scores = {k: v for k, v in scores.items() if k in images}
    save_scores(scores)
    return scores


def save_scores(scores):
    SCORES_FILE.write_text(json.dumps(scores, indent=2))


def names_in_category(scores, cat):
    return [n for n in scores.keys() if category_of(n) == cat]


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
    .switcher { margin-bottom:1.5rem; display:flex; justify-content:center; gap:0.6rem; flex-wrap:wrap; }
    .switcher a {
      padding:0.5rem 1.3rem; border-radius:999px; text-decoration:none;
      color:#ccc; border:1px solid rgba(255,255,255,0.15); font-weight:600;
      font-size:0.9rem; transition:0.15s; background:rgba(255,255,255,0.03);
    }
    .switcher a.active {
      background: linear-gradient(90deg,#ff4d8d,#ff9d4d); color:#111; border-color:transparent;
    }
    .arena {
      display:flex; justify-content:center; align-items:stretch; gap:1.2rem;
      margin-top:1rem; flex-wrap:wrap; max-width:760px; margin-left:auto; margin-right:auto;
    }
    .card {
      cursor:pointer; border-radius:18px; overflow:hidden; position:relative;
      flex:1 1 260px; max-width:340px; min-width:150px;
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
      font-weight:900; font-size:1.3rem; color:#ff9d4d; min-width:2rem;
    }
    #status { margin-top:1.3rem; font-size:0.9rem; color:#999; min-height:1.2rem; }
    a.link {
      display:inline-block; margin-top:1.6rem; color:#ffd93d; text-decoration:none;
      font-weight:600; border-bottom:1px solid rgba(255,217,61,0.4); padding-bottom:2px;
    }
    @media (max-width: 480px) {
      .arena { gap:0.7rem; }
      .vs { min-width:1.2rem; font-size:1rem; }
    }
  </style>
</head>
<body>
  <div class="brand">Facemash</div>
  <div class="tagline">Who is the winner?</div>
  <div class="switcher">
    {% for key, label in categories.items() %}
      <a href="/?cat={{ key }}" class="{{ 'active' if key == cat else '' }}">{{ label }}</a>
    {% endfor %}
  </div>
  <div class="arena" id="arena"></div>
  <div id="status"></div>
  <p><a class="link" href="/leaderboard?cat={{ cat }}">🏆 View {{ categories[cat] }} leaderboard</a></p>

<script>
const CAT = "{{ cat }}";

function renderPair(pair) {
  const arena = document.getElementById('arena');
  arena.innerHTML = '';
  if (!pair || pair.length < 2) {
    arena.innerHTML = '<p>Not enough images in this category yet.</p>';
    return;
  }
  const left = document.createElement('div');
  left.className = 'card';
  left.innerHTML = `<img src="/static/images/${pair[0]}">`;
  left.onclick = () => vote(pair[0], pair[1]);

  const vs = document.createElement('div');
  vs.className = 'vs';
  vs.textContent = 'VS';

  const right = document.createElement('div');
  right.className = 'card';
  right.innerHTML = `<img src="/static/images/${pair[1]}">`;
  right.onclick = () => vote(pair[1], pair[0]);

  arena.appendChild(left);
  arena.appendChild(vs);
  arena.appendChild(right);
}

async function loadPair() {
  const res = await fetch('/api/pair?cat=' + CAT);
  const data = await res.json();
  renderPair(data.pair);
}

async function vote(winner, loser) {
  document.getElementById('status').innerText = 'Recording vote...';
  await fetch('/api/vote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({winner, loser})
  });
  document.getElementById('status').innerText = '';

  const res = await fetch('/api/opponent?cat=' + CAT + '&exclude=' + encodeURIComponent(winner));
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
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FACEMASH Leaderboard</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin:0; font-family: 'Segoe UI', system-ui, sans-serif;
      background: radial-gradient(circle at top, #1b1030 0%, #0a0612 60%, #050308 100%);
      color:#f5f5f7; text-align:center; min-height:100vh; padding:1.5rem 1rem 3rem;
    }
    .brand {
      font-size: clamp(1.8rem, 7vw, 2.6rem); font-weight:900; letter-spacing:0.06em;
      margin: 0.5rem 0 0.1rem; background: linear-gradient(90deg,#ff4d8d,#ff9d4d,#ffd93d);
      -webkit-background-clip:text; background-clip:text; color:transparent;
      text-transform:uppercase;
    }
    .subhead { font-size:1.1rem; font-weight:600; color:#ccc; margin-bottom:1.2rem; }
    .switcher { margin-bottom:1.5rem; display:flex; justify-content:center; gap:0.6rem; flex-wrap:wrap; }
    .switcher a {
      padding:0.5rem 1.3rem; border-radius:999px; text-decoration:none;
      color:#ccc; border:1px solid rgba(255,255,255,0.15); font-weight:600;
      font-size:0.9rem; transition:0.15s; background:rgba(255,255,255,0.03);
    }
    .switcher a.active {
      background: linear-gradient(90deg,#ff4d8d,#ff9d4d); color:#111; border-color:transparent;
    }
    .champion {
      margin: 0 auto 1.8rem; padding: 1.6rem; max-width: 340px;
      border: 2px solid #ffd93d; border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,217,61,0.12), rgba(255,77,141,0.04));
      box-shadow: 0 10px 30px rgba(255,217,61,0.15);
    }
    .champion-label {
      color:#ffd93d; font-weight:800; letter-spacing:0.08em; text-transform:uppercase;
      font-size:0.8rem;
    }
    .champion img {
      width:170px; height:170px; object-fit:cover; border-radius:14px; margin:0.9rem 0;
      box-shadow:0 6px 18px rgba(0,0,0,0.5);
    }
    .champion-name { font-size:1.05rem; font-weight:600; word-break:break-word; }
    .champion-stats { color:#aaa; font-size:0.85rem; margin-top:0.3rem; }

    .board { max-width:520px; margin:0 auto; }
    .row {
      display:flex; align-items:center; gap:0.8rem; padding:0.6rem 0.4rem;
      border-bottom:1px solid rgba(255,255,255,0.07); text-align:left;
    }
    .rank { width:1.6rem; font-weight:800; color:#888; flex-shrink:0; }
    .row img { width:48px; height:48px; object-fit:cover; border-radius:8px; flex-shrink:0; }
    .name { flex:1; font-size:0.9rem; word-break:break-word; }
    .stats { font-size:0.8rem; color:#999; white-space:nowrap; }
    .elo { font-weight:700; color:#ff9d4d; }

    a.link {
      display:inline-block; margin-top:1.8rem; color:#ffd93d; text-decoration:none;
      font-weight:600; border-bottom:1px solid rgba(255,217,61,0.4); padding-bottom:2px;
    }
  </style>
</head>
<body>
  <div class="brand">Facemash</div>
  <div class="subhead">{{ categories[cat] }} Leaderboard</div>
  <div class="switcher">
    {% for key, label in categories.items() %}
      <a href="/leaderboard?cat={{ key }}" class="{{ 'active' if key == cat else '' }}">{{ label }}</a>
    {% endfor %}
  </div>

  {% if ranked %}
  {% set champ_name, champ = ranked[0] %}
  <div class="champion">
    <div class="champion-label">🏆 Current Champion</div>
    <img src="/static/images/{{ champ_name }}">
    <div class="champion-name">{{ champ_name }}</div>
    <div class="champion-stats">Elo {{ champ.elo }} · {{ champ.wins }}W / {{ champ.losses }}L</div>
  </div>
  {% endif %}

  <div class="board">
    {% for name, s in ranked %}
    <div class="row">
      <div class="rank">#{{ loop.index }}</div>
      <img src="/static/images/{{ name }}">
      <div class="name">{{ name }}</div>
      <div class="stats"><span class="elo">{{ s.elo }}</span> · {{ s.wins }}W/{{ s.losses }}L</div>
    </div>
    {% endfor %}
  </div>
  <p><a class="link" href="/?cat={{ cat }}">⬅ Back to voting</a></p>
</body>
</html>
"""


def resolve_cat(request_args):
    cat = request_args.get("cat", "m")
    return cat if cat in CATEGORIES else "m"


@app.route("/")
def index():
    cat = resolve_cat(request.args)
    return render_template_string(PAGE_TEMPLATE, cat=cat, categories=CATEGORIES)


@app.route("/api/pair")
def api_pair():
    scores = load_scores()
    cat = resolve_cat(request.args)
    names = names_in_category(scores, cat)
    if len(names) < 2:
        return jsonify({"pair": []})
    pair = random.sample(names, 2)
    return jsonify({"pair": pair})


@app.route("/api/opponent")
def api_opponent():
    scores = load_scores()
    cat = resolve_cat(request.args)
    exclude = request.args.get("exclude", "")
    candidates = [n for n in names_in_category(scores, cat) if n != exclude]
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
    if category_of(winner) != category_of(loser):
        return jsonify({"error": "Images must be from the same category."}), 400
    update_elo(scores, winner, loser)
    return jsonify({"ok": True})


@app.route("/leaderboard")
def leaderboard():
    scores = load_scores()
    cat = resolve_cat(request.args)
    pool = {n: s for n, s in scores.items() if category_of(n) == cat}
    ranked = sorted(pool.items(), key=lambda kv: kv[1]["elo"], reverse=True)
    return render_template_string(
        LEADERBOARD_TEMPLATE, ranked=ranked, cat=cat, categories=CATEGORIES
    )


if __name__ == "__main__":
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    app.run(debug=True)
