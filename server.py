from flask import Flask, request, jsonify, render_template_string
import sqlite3
import datetime
import random
import string

app = Flask(__name__)
DB = 'licenses.db'
APP_SECRET = "sk_excelmerger_2026" # must match the one in your exe

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS licenses
                 (key TEXT PRIMARY KEY, plan TEXT, credits INTEGER, 
                  expires TEXT, machine_id TEXT, total_used INTEGER)''')
    conn.commit()
    conn.close()

def generate_key(prefix):
    rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{prefix}-{rand}"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

@app.route('/verify', methods=['POST'])
def api():
    # security check
    if request.headers.get('X-App-Key') != APP_SECRET:
        return jsonify({"status": "ERROR", "message": "Invalid App"}), 403

    data = request.json
    key = data['key']
    machine_id = data['machine_id']
    action = data['action']
    
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM licenses WHERE key=?", (key,))
    lic = c.fetchone()

    if not lic:
        return jsonify({"status": "INVALID"})

    # check expiry for 30 day plan
    if lic['expires'] and lic['expires'] != "Never":
        if datetime.datetime.now() > datetime.datetime.fromisoformat(lic['expires']):
            return jsonify({"status": "EXPIRED"})

    if action == "activate":
        if lic['machine_id'] and lic['machine_id'] != "ANY" and lic['machine_id'] != machine_id:
            return jsonify({"status": "ALREADY_USED"})
        c.execute("UPDATE licenses SET machine_id=? WHERE key=?", (machine_id, key))
        conn.commit()
        return jsonify({"status": "OK", "plan": lic['plan'], "credits_left": lic['credits']})

    if action == "use_credit":
        if lic['credits'] == 0:
            return jsonify({"status": "NO_CREDITS"})
        if lic['credits'] != -1: # -1 = 30 day unlimited
            new_credits = lic['credits'] - 1
            new_used = lic['total_used'] + 1
            c.execute("UPDATE licenses SET credits=?, total_used=? WHERE key=?", (new_credits, new_used, key))
            conn.commit()
        return jsonify({"status": "OK", "credits_left": lic['credits']-1 if lic['credits'] != -1 else -1})
    
    return jsonify({"status": "ERROR"})

# ADMIN PAGE TO CREATE KEYS - ONLY 3 PLANS NOW
ADMIN_HTML = """
<h2>ExcelMergerPro Admin</h2>
<form method=post>
  Plan: 
  <select name=plan>
    <option value="5 Merges">5 Merges</option>
    <option value="10 Merges">10 Merges</option>
    <option value="30 Day Unlimited">30 Day Unlimited</option>
  </select>
  <input type=submit value="Create Key">
</form>
<h3>Existing Keys</h3>
<table border=1><tr><th>Key</th><th>Plan</th><th>Credits</th><th>Expires</th><th>Machine</th><th>Used</th></tr>
{% for lic in licenses %}
<tr>
  <td>{{lic.key}}</td>
  <td>{{lic.plan}}</td>
  <td>{{'Unlimited' if lic.credits == -1 else lic.credits}}</td>
  <td>{{'Never' if lic.expires == 'Never' else lic.expires[:10]}}</td>
  <td>{{lic.machine_id or 'None'}}</td>
  <td>{{lic.total_used}}</td>
</tr>
{% endfor %}</table>
"""

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    conn = get_db()
    if request.method == 'POST':
        plan = request.form['plan']
        if plan == "5 Merges": 
            credits, prefix, expires = 5, "EMP-5", "Never"
        elif plan == "10 Merges": 
            credits, prefix, expires = 10, "EMP-10", "Never"
        elif plan == "30 Day Unlimited": 
            credits, prefix, expires = -1, "EMP-30D", (datetime.datetime.now() + datetime.timedelta(days=30)).isoformat()
        
        key = generate_key(prefix)
        conn.execute("INSERT INTO licenses VALUES (?,?,?,?,?,?)", 
                     (key, plan, credits, expires, None, 0))
        conn.commit()
        
    licenses = conn.execute("SELECT * FROM licenses ORDER BY key DESC").fetchall()
    return render_template_string(ADMIN_HTML, licenses=licenses)

if __name__ == '__main__':
    init_db()
    app.run()
