from flask import Flask, request, jsonify, render_template_string
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import os, secrets, string

app = Flask(__name__)

# FIX: Render gives postgres:// but SQLAlchemy needs postgresql://
DB_PATH = os.environ.get("DATABASE_URL", "sqlite:///licenses.db")
if DB_PATH.startswith("postgres://"):
    DB_PATH = DB_PATH.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DB_PATH
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

APP_KEY = "sk_excelmerger_2026"

class License(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), unique=True, nullable=False)
    plan = db.Column(db.String(50), nullable=False)
    credits_left = db.Column(db.Integer, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=True)
    machine_id = db.Column(db.String(100), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        exp = "Never"
        if self.expires_at:
            exp = self.expires_at.replace(tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
        return {
            "id": self.id, "key": self.key, "plan": self.plan, 
            "credits_left": self.credits_left,
            "expires_at": exp,
            "machine_id": self.machine_id or "Not Activated"
        }

# Create tables on startup
with app.app_context(): 
    db.create_all()

def gen_key(): 
    # FIXED: string.digits not DIGITS
    return "EMP-" + ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(12))

# --- YOUR APP ENDPOINT ---
@app.route("/verify", methods=["POST"])
def verify():
    if request.headers.get("X-App-Key") != APP_KEY: 
        return jsonify({"status": "INVALID_KEY"}), 403
    
    data = request.get_json()
    key = data.get("key")
    machine_id = data.get("machine_id")
    action = data.get("action")
    
    license = License.query.filter_by(key=key).first()
    if not license: 
        return jsonify({"status": "INVALID"})
    
    now = datetime.now(timezone.utc)
    if license.credits_left == -1 and license.expires_at and license.expires_at.replace(tzinfo=timezone.utc) < now: 
        return jsonify({"status": "EXPIRED"})
    if license.credits_left == 0: 
        return jsonify({"status": "NO_CREDITS"})
    if license.machine_id and license.machine_id != machine_id: 
        return jsonify({"status": "ALREADY_USED"})
    
    if action == "check" or action == "activate":
        if action == "activate" and not license.machine_id: 
            license.machine_id = machine_id
            db.session.commit()
        return jsonify({"status": "OK", **license.to_dict()})
    
    elif action == "use_credit":
        if license.credits_left > 0: 
            license.credits_left -= 1
            db.session.commit()
        return jsonify({"status": "OK", **license.to_dict()})
    
    return jsonify({"status": "UNKNOWN_ACTION"})

# --- ADMIN PAGE ---
HTML = """
<!doctype html>
<html>
<head><title>ExcelMergerPro Admin</title>
<style>body{font-family:sans-serif;padding:20px;background:#f4f4f4} 
.btn{background:#2563eb;color:white;padding:10px 20px;border:none;border-radius:5px;cursor:pointer} 
table{width:100%;border-collapse:collapse;margin-top:20px;background:white} 
th,td{border:1px solid #ddd;padding:8px;text-align:left} 
th{background:#2563eb;color:white} code{background:#eee;padding:2px 5px}</style>
</head>
<body>
<h1>ExcelMergerPro License Admin</h1>
<form action="/admin/generate" method="post">
  <label><b>Select Plan:</b></label>
  <select name="plan">
    <option>5 Merges</option>
    <option>10 Merges</option>
    <option>30 Day Unlimited</option>
  </select>
  <button class="btn" type="submit">+ Create Key</button>
</form>

<h2>All Keys</h2>
<table>
  <tr><th>ID</th><th>Key</th><th>Plan</th><th>Credits Left</th><th>Expires</th><th>Machine</th></tr>
  {% for l in licenses %}
  <tr>
    <td>{{l.id}}</td>
    <td><code>{{l.key}}</code></td>
    <td>{{l.plan}}</td>
    <td>{{'Unlimited' if l.credits_left==-1 else l.credits_left}}</td>
    <td>{{l.expires_at}}</td>
    <td>{{l.machine_id}}</td>
  </tr>
  {% endfor %}
</table>
</body></html>
"""

@app.route("/admin", methods=["GET"])
def admin_page():
    licenses = License.query.order_by(License.id.desc()).all()
    return render_template_string(HTML, licenses=[l.to_dict() for l in licenses])

@app.route("/admin/generate", methods=["POST"])
def generate_key():
    plan = request.form.get("plan")
    key = gen_key()
    credits = 5 if plan == "5 Merges" else 10 if plan == "10 Merges" else -1
    expires_at = datetime.now(timezone.utc) + timedelta(days=30) if plan == "30 Day Unlimited" else None
    new_license = License(key=key, plan=plan, credits_left=credits, expires_at=expires_at)
    db.session.add(new_license)
    db.session.commit()
    return admin_page() # reload page with new key in table

if __name__ == "__main__": 
    app.run(host="0.0.0.0", port=5000)

