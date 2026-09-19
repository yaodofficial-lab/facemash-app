"""
Facemash-style app: head-to-head image voting with Elo-based ranking.

Setup:
    pip install flask
    mkdir static/images
    # drop your own approved images (jpg/png) into static/images/
    python facemash.py
    # open http://127.0.0.1:5000

Data is stored in scores.json (created automatically). Swap in a real
database if you need persistence beyond a single machine / process.
"""

import json
import os
import random
from pathlib import Path
from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

IMAGE_DIR = Path("static/images")
SCORES_FILE = Path("scores.json")
K_FACTOR = 32          # Elo sensitivity
STARTING_ELO = 1200


def load_scores():
    """Load existing Elo scores, or initialize new ones from images on disk."""
    images = sorted(
        f.name for f in IMAGE_DIR.glob("*")
        if f.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}
    )
    if not images:
        raise RuntimeError(f"No images found in {IMAGE_DIR}/ — add some first.")

    scores = {}
    if SCORES_FILE.exists():
        scores = json.loads(SCORES_FILE.read_text())

    for name in images:
        scores.setdefault(name, {"elo": STARTING_ELO, "wins": 0, "losses": 0})

    # drop entries for images that no longer exist
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
  <title>Facemash</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#111; color:#eee; text-align:center; }
    h1 { margin-top: 2rem; }
    .arena { display:flex; justify-content:center; gap:2rem; margin-top:2rem; flex-wrap:wrap; }
    .card { cursor:pointer; border:3px solid transparent; border-radius:10px; transition:0.15s; }
    .card:hover { border-color:#4caf50; transform:scale(1.02); }
    .card img { width:320px; height:320px; object-fit:cover; border-radius:8px; display:block; }
    #status { margin-top:1.5rem; font-size:0.9rem; color:#888; }
    a { color:#4caf50; }
  </style>
</head>
<body>
  <h1>Which one wins?</h1>
  <div class="arena" id="arena"></div>
  <div id="status"></div>
  <p><a href="/leaderboard">View leaderboard</a></p>

<script>
async function loadPair() {
  const res = await fetch('/api/pair');
  const data = await res.json();
  const arena = document.getElementById('arena');
  arena.innerHTML = '';
  data.pair.forEach(img => {
    const div = document.createElement('div');
    div.className = 'card';
    div.innerHTML = `<img src="/static/images/${img}">`;
    div.onclick = () => vote(img, data.pair.find(x => x !== img));
    arena.appendChild(div);
  });
}

async function vote(winner, loser) {
  document.getElementById('status').innerText = 'Recording vote...';
  await fetch('/api/vote', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({winner, loser})
  });
  document.getElementById('status').innerText = '';
  loadPair();
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
  <title>Leaderboard</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#111; color:#eee; text-align:center; }
    table { margin:2rem auto; border-collapse:collapse; }
    td, th { padding:0.5rem 1.2rem; border-bottom:1px solid #333; }
    img { width:60px; height:60px; object-fit:cover; border-radius:6px; vertical-align:middle; }
    a { color:#4caf50; }
    .champion {
      margin: 2rem auto 1rem;
      padding: 1.5rem;
      max-width: 360px;
      border: 2px solid #ffd700;
      border-radius: 14px;
      background: linear-gradient(180deg, rgba(255,215,0,0.08), transparent);
    }
    .champion-label { color:#ffd700; font-weight:600; letter-spacing:0.05em; text-transform:uppercase; font-size:0.85rem; }
    .champion img { width:180px; height:180px; border-radius:10px; margin:0.8rem 0; }
    .champion-name { font-size:1.1rem; margin-top:0.3rem; }
    .champion-stats { color:#aaa; font-size:0.85rem; margin-top:0.3rem; }
  </style>
</head>
<body>
  <h1>Leaderboard</h1>

  {% if ranked %}
  {% set champ_name, champ = ranked[0] %}
  <div class="champion">
    <div class="champion-label">🏆 Current Champion</div>
    <img src="/static/images/{{ champ_name }}">
    <div class="champion-name">{{ champ_name }}</div>
    <div class="champion-stats">Elo {{ champ.elo }} · {{ champ.wins }}W / {{ champ.losses }}L</div>
  </div>
  {% endif %}

  <table>
    <tr><th>#</th><th>Image</th><th>Elo</th><th>W</th><th>L</th></tr>
    {% for name, s in ranked %}
    <tr>
      <td>{{ loop.index }}</td>
      <td><img src="/static/images/{{ name }}"> {{ name }}</td>
      <td>{{ s.elo }}</td>
      <td>{{ s.wins }}</td>
      <td>{{ s.losses }}</td>
    </tr>
    {% endfor %}
  </table>
  <p><a href="/">Back to voting</a></p>
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
        return jsonify({"error": "Need at least 2 images."}), 400
    pair = random.sample(names, 2)
    return jsonify({"pair": pair})


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
