
import streamlit as st
import sqlite3
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import hashlib
import secrets
import unicodedata
import html
import streamlit.components.v1 as components

DB_PATH = Path(__file__).with_name("office_tasks.db")

st.set_page_config(
    page_title="Office Task Desk",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ----------------------------- DATABASE -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str, salt: str | None = None):
    salt = salt or secrets.token_hex(16)
    pwd_hash = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return salt, pwd_hash

def verify_password(password: str, salt: str, pwd_hash: str):
    test = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(test, pwd_hash)

def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def contains_emoji_or_symbol(text: str) -> bool:
    """Reject emoji-style symbols and control joiners/variation selectors."""
    if not text:
        return False
    for ch in text:
        cp = ord(ch)
        cat = unicodedata.category(ch)
        if cp in (0x200D, 0xFE0F):  # ZWJ / variation selector
            return True
        if 0x1F1E6 <= cp <= 0x1F1FF:  # regional indicators
            return True
        if 0x1F300 <= cp <= 0x1FAFF:  # most emoji blocks
            return True
        if cat in ("So", "Sk"):
            return True
    return False

def validate_text_fields(**fields):
    bad = [name for name, value in fields.items() if contains_emoji_or_symbol(value or "")]
    if bad:
        return False, "Emoji/symbol characters are not allowed in: " + ", ".join(bad)
    return True, ""

def copy_ticket_button(ticket_no: str, key: str):
    safe = html.escape(ticket_no)
    components.html(
        f"""
        <button id="{key}" style="
            border:1px solid #d1d5db;
            background:#ffffff;
            padding:7px 10px;
            border-radius:8px;
            cursor:pointer;
            font-weight:600;
            font-family:Arial,sans-serif;">
            Copy {safe}
        </button>
        <script>
        const btn = document.getElementById("{key}");
        btn.onclick = async () => {{
            await navigator.clipboard.writeText("{safe}");
            btn.innerText = "Copied";
            setTimeout(() => btn.innerText = "Copy {safe}", 1300);
        }};
        </script>
        """,
        height=42,
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_salt TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('Manager','Employee')),
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT UNIQUE,
            customer_name TEXT NOT NULL,
            loan_type TEXT,
            surrogate TEXT,
            assignment_mode TEXT NOT NULL DEFAULT 'Individual',
            assigned_to INTEGER,
            claimed_by INTEGER,
            priority TEXT,
            due_date TEXT,
            manager_remarks TEXT,
            overall_status TEXT NOT NULL DEFAULT 'Open',
            created_by INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(assigned_to) REFERENCES users(id),
            FOREIGN KEY(claimed_by) REFERENCES users(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            task_name TEXT NOT NULL,
            lender_name TEXT,
            details TEXT,
            status TEXT NOT NULL DEFAULT 'Open',
            assigned_to INTEGER,
            claimed_by INTEGER,
            login_id TEXT,
            employee_remark TEXT,
            created_by INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(assigned_to) REFERENCES users(id),
            FOREIGN KEY(claimed_by) REFERENCES users(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)


    cur.execute("""
        CREATE TABLE IF NOT EXISTS comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            comment_text TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            ticket_id INTEGER,
            task_id INTEGER,
            message TEXT NOT NULL,
            is_read INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id),
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(task_id) REFERENCES ticket_tasks(id)
        )
    """)

    # Backward-compatible columns for existing databases
    for stmt in [
        "ALTER TABLE ticket_tasks ADD COLUMN assigned_at TEXT",
        "ALTER TABLE tickets ADD COLUMN assignment_note TEXT"
    ]:
        try:
            cur.execute(stmt)
        except sqlite3.OperationalError:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            task_id INTEGER,
            user_id INTEGER,
            action TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(task_id) REFERENCES ticket_tasks(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Create default manager if no manager exists
    exists = cur.execute("SELECT id FROM users WHERE role='Manager' LIMIT 1").fetchone()
    if not exists:
        salt, pwd_hash = hash_password("1234")
        cur.execute("""
            INSERT INTO users(username,password_salt,password_hash,full_name,role,active,created_at)
            VALUES (?,?,?,?,?,?,?)
        """, ("manager", salt, pwd_hash, "Manager", "Manager", 1, now()))

    conn.commit()
    conn.close()

def add_activity(ticket_id, user_id, action, task_id=None):
    conn = get_conn()
    conn.execute("""
        INSERT INTO activity_log(ticket_id,task_id,user_id,action,created_at)
        VALUES (?,?,?,?,?)
    """, (ticket_id, task_id, user_id, action, now()))
    conn.commit()
    conn.close()

def notify_user(user_id, message, ticket_id=None, task_id=None):
    if not user_id:
        return
    conn = get_conn()
    conn.execute("""
        INSERT INTO notifications(user_id,ticket_id,task_id,message,is_read,created_at)
        VALUES (?,?,?,?,0,?)
    """, (user_id,ticket_id,task_id,message,now()))
    conn.commit()
    conn.close()

def notify_all_active_employees(message, ticket_id=None, task_id=None, exclude_user_id=None):
    conn = get_conn()
    rows = conn.execute("SELECT id FROM users WHERE role='Employee' AND active=1").fetchall()
    for r in rows:
        if exclude_user_id and r["id"] == exclude_user_id:
            continue
        conn.execute("""
            INSERT INTO notifications(user_id,ticket_id,task_id,message,is_read,created_at)
            VALUES (?,?,?,?,0,?)
        """, (r["id"],ticket_id,task_id,message,now()))
    conn.commit()
    conn.close()

def unread_notification_count(user_id):
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id=? AND is_read=0",
        (user_id,)
    ).fetchone()
    conn.close()
    return row["c"] if row else 0

def comments_for(ticket_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT c.*,u.full_name
        FROM comments c
        LEFT JOIN users u ON c.user_id=u.id
        WHERE c.ticket_id=?
        ORDER BY c.id ASC
    """,(ticket_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def recalc_ticket(ticket_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT status FROM ticket_tasks WHERE ticket_id=?",
        (ticket_id,)
    ).fetchall()
    statuses = [r["status"] for r in rows]

    if statuses and all(s == "Done" for s in statuses):
        overall = "Completed"
    elif statuses and any(s in ("In Progress","Done","Documents Required","Rejected","Rework") for s in statuses):
        overall = "In Progress"
    else:
        overall = "Open"

    conn.execute(
        "UPDATE tickets SET overall_status=?, updated_at=? WHERE id=?",
        (overall, now(), ticket_id)
    )
    conn.commit()
    conn.close()

def employees(active_only=True):
    conn = get_conn()
    q = "SELECT id,username,full_name,active FROM users WHERE role='Employee'"
    if active_only:
        q += " AND active=1"
    q += " ORDER BY full_name"
    rows = [dict(r) for r in conn.execute(q).fetchall()]
    conn.close()
    return rows

def get_ticket_df(where="", params=()):
    conn = get_conn()
    q = """
        SELECT
            t.*,
            a.full_name AS assigned_name,
            c.full_name AS claimed_name,
            cr.full_name AS created_name
        FROM tickets t
        LEFT JOIN users a ON t.assigned_to=a.id
        LEFT JOIN users c ON t.claimed_by=c.id
        LEFT JOIN users cr ON t.created_by=cr.id
    """
    if where:
        q += " WHERE " + where
    q += " ORDER BY t.id DESC"
    rows = [dict(r) for r in conn.execute(q, params).fetchall()]
    conn.close()
    return pd.DataFrame(rows)

def tasks_for(ticket_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT
            tt.*,
            a.full_name AS assigned_name,
            c.full_name AS claimed_name
        FROM ticket_tasks tt
        LEFT JOIN users a ON tt.assigned_to=a.id
        LEFT JOIN users c ON tt.claimed_by=c.id
        WHERE tt.ticket_id=?
        ORDER BY tt.id
    """, (ticket_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

init_db()

# ----------------------------- STYLE -----------------------------
st.markdown("""
<style>
html, body, [class*="css"] { font-family: "Segoe UI", Arial, sans-serif; }
.block-container { padding-top: 1.2rem; padding-bottom: 2rem; max-width: 1500px; }
h1 { font-size: 2rem !important; font-weight: 780 !important; letter-spacing: -0.4px; }
h2, h3 { font-weight: 700 !important; }
section[data-testid="stSidebar"] { border-right: 1px solid #e5e7eb; }
section[data-testid="stSidebar"] .block-container { padding-top: 1.1rem; }

.brand-title { font-size: 1.15rem; font-weight: 800; color: #111827; }
.brand-subtitle { font-size: .78rem; color:#6b7280; margin-bottom: 12px; }
.page-subtitle { color:#6b7280; margin-top:-6px; margin-bottom:16px; font-size:.93rem; }

.kpi-grid { display:grid; grid-template-columns:repeat(5,minmax(120px,1fr)); gap:12px; margin:10px 0 22px; }
.kpi-card { background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:16px 18px; box-shadow:0 2px 8px rgba(15,23,42,.04); }
.kpi-label { color:#6b7280; font-size:.8rem; font-weight:650; }
.kpi-value { color:#111827; font-size:1.7rem; font-weight:800; }

.ticket-card { border:1px solid #e5e7eb; border-left:4px solid #2563eb; border-radius:14px; padding:15px 17px; margin-bottom:10px; background:#fff; box-shadow:0 2px 8px rgba(15,23,42,.04); }
.ticket-title { font-size:1.02rem; font-weight:780; color:#111827; }
.small-muted { color:#6b7280; font-size:.86rem; margin-top:5px; }
.badge { display:inline-block; padding:4px 9px; border-radius:999px; font-size:.75rem; font-weight:750; margin-right:5px; margin-top:8px; }
.b-open { background:#eff6ff; color:#1d4ed8; }
.b-progress { background:#fff7ed; color:#c2410c; }
.b-done { background:#ecfdf5; color:#047857; }
.b-high { background:#fef2f2; color:#b91c1c; }
.b-med { background:#fffbeb; color:#b45309; }
.b-normal { background:#f3f4f6; color:#4b5563; }
.b-team { background:#f5f3ff; color:#6d28d9; }
.b-claimed { background:#ecfeff; color:#0f766e; }

.task-box { border:1px solid #e5e7eb; border-radius:12px; padding:13px 15px; margin-bottom:10px; background:#fafafa; }

.stButton > button, .stDownloadButton > button { border-radius:10px; font-weight:650; }
div[data-baseweb="input"] > div, div[data-baseweb="select"] > div, textarea { border-radius:10px !important; }

@media (max-width:900px){ .kpi-grid{grid-template-columns:repeat(2,minmax(120px,1fr));} }
</style>
""", unsafe_allow_html=True)

# ----------------------------- SESSION / LOGIN -----------------------------
if "user" not in st.session_state:
    st.session_state.user = None

def login_screen():
    st.title("Office Task Desk")
    st.markdown('<div class="page-subtitle">Internal ticket, task and login tracking</div>', unsafe_allow_html=True)
    c1,c2,c3 = st.columns([1,1.05,1])
    with c2:
        with st.container(border=True):
            st.subheader("Sign in")
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            if st.button("Login", type="primary", use_container_width=True):
                conn = get_conn()
                row = conn.execute(
                    "SELECT * FROM users WHERE username=? AND active=1",
                    (username.strip(),)
                ).fetchone()
                conn.close()
                if row and verify_password(password, row["password_salt"], row["password_hash"]):
                    st.session_state.user = dict(row)
                    st.rerun()
                else:
                    st.error("Invalid username/password or inactive account.")
            st.caption("Default first login: manager / 1234")

if not st.session_state.user:
    login_screen()
    st.stop()

user = st.session_state.user

# ----------------------------- SIDEBAR -----------------------------
st.sidebar.markdown("""
<div class="brand-title">✅ Office Task Desk</div>
<div class="brand-subtitle">Ticket & Team Task Tracker</div>
""", unsafe_allow_html=True)
st.sidebar.write(f"**{user['full_name']}**")
st.sidebar.caption(user["role"])

notif_count = unread_notification_count(user["id"])
st.sidebar.caption(f"Notifications: {notif_count}")

if user["role"] == "Manager":
    menu = st.sidebar.radio("Menu", [
        "Dashboard",
        "Today",
        "Raise Ticket",
        "All Tickets",
        "Team Pool",
        "Employees",
        "Notifications",
        "Reports"
    ])
else:
    menu = st.sidebar.radio("Menu", [
        "My Dashboard",
        "Today",
        "My Tickets",
        "Team Pool",
        "Notifications"
    ])

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()

# ----------------------------- UI HELPERS -----------------------------
def render_kpis(items):
    cards = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'
        for label, value in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

def render_ticket_card(row):
    status = row.get("overall_status","Open")
    priority = row.get("priority","Normal")
    sclass = {"Open":"b-open","In Progress":"b-progress","Completed":"b-done"}.get(status,"b-open")
    pclass = {"Urgent":"b-high","High":"b-high","Medium":"b-med","Normal":"b-normal"}.get(priority,"b-normal")
    mode = row.get("assignment_mode","Individual")
    owner = row.get("claimed_name") or row.get("assigned_name") or "Unassigned"
    if row.get("assignment_mode") == "Team":
        owners = ticket_task_ownership(row["id"])
        unique = sorted({x["owner"] for x in owners if x["owner"] != "Available"})
        if len(unique) > 1:
            owner = "Multiple Team Members"
        elif len(unique) == 1:
            owner = unique[0]
    due = row.get("due_date") or "-"
    overdue = False
    try:
        overdue = bool(row.get("due_date")) and row.get("due_date") < date.today().isoformat() and status != "Completed"
    except Exception:
        overdue = False
    extra = '<span class="badge b-team">TEAM POOL</span>' if mode == "Team" else ""
    claimed = f'<span class="badge b-claimed">Handled By: {owner}</span>' if owner != "Unassigned" else ""
    st.markdown(f"""
    <div class="ticket-card">
      <div class="ticket-title">{row['ticket_no']} &nbsp;•&nbsp; {row['customer_name']}</div>
      <div class="small-muted">💼 {row.get('loan_type','-')} &nbsp; • &nbsp; 🧾 {row.get('surrogate','-')} &nbsp; • &nbsp; 📅 {due}</div>
      <div>
        <span class="badge {pclass}">{priority}</span>
        <span class="badge {sclass}">{status}</span>
        {extra}{claimed}{"<span class=\"badge b-high\">OVERDUE</span>" if overdue else ""}
      </div>
    </div>
    """, unsafe_allow_html=True)

def can_employee_view_ticket(row):
    if user["role"] == "Manager":
        return True
    if row["assignment_mode"] == "Team":
        return True
    return row.get("assigned_to") == user["id"] or row.get("claimed_by") == user["id"]

def claim_ticket_atomic(ticket_id, user_id):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT assignment_mode,claimed_by FROM tickets WHERE id=?",
            (ticket_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            return False, "Ticket not found."
        if row["assignment_mode"] != "Team":
            conn.rollback()
            return False, "This is not a team-pool ticket."
        if row["claimed_by"] is not None:
            conn.rollback()
            return False, "This ticket has already been taken by another employee."
        conn.execute(
            "UPDATE tickets SET claimed_by=?, updated_at=? WHERE id=? AND claimed_by IS NULL",
            (user_id, now(), ticket_id)
        )
        conn.commit()
        return True, "Ticket claimed successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def claim_task_atomic(task_id, user_id):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id,ticket_id,claimed_by,assigned_to,status FROM ticket_tasks WHERE id=?",
            (task_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            return False, "Task not found.", None
        if row["claimed_by"] is not None:
            conn.rollback()
            return False, "This task has already been taken.", row["ticket_id"]
        if row["status"] == "Done":
            conn.rollback()
            return False, "This task is already completed.", row["ticket_id"]
        conn.execute("""
            UPDATE ticket_tasks
            SET claimed_by=?, status='In Progress', updated_at=?
            WHERE id=? AND claimed_by IS NULL
        """, (user_id, now(), task_id))
        conn.commit()
        return True, "Task claimed successfully.", row["ticket_id"]
    except Exception as e:
        conn.rollback()
        return False, str(e), None
    finally:
        conn.close()



def claim_selected_tasks_atomic(ticket_id, task_ids, user_id):
    if not task_ids:
        return False, "Select at least one task."
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        marks = ",".join("?" for _ in task_ids)
        rows = conn.execute(
            f"""SELECT id,task_name,claimed_by,assigned_to,status
                FROM ticket_tasks
                WHERE ticket_id=? AND id IN ({marks})""",
            [ticket_id] + list(task_ids)
        ).fetchall()
        if len(rows) != len(task_ids):
            conn.rollback()
            return False, "Some selected tasks are no longer available."
        unavailable = [
            r["task_name"] for r in rows
            if r["claimed_by"] is not None or r["assigned_to"] is not None or r["status"] == "Done"
        ]
        if unavailable:
            conn.rollback()
            return False, "Already taken/completed: " + ", ".join(unavailable)
        for task_id in task_ids:
            conn.execute("""
                UPDATE ticket_tasks
                SET claimed_by=?,status='In Progress',assigned_at=?,updated_at=?
                WHERE id=? AND claimed_by IS NULL AND assigned_to IS NULL AND status!='Done'
            """,(user_id,now(),now(),task_id))
        conn.commit()
        return True, f"{len(task_ids)} task(s) claimed successfully."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def claim_full_ticket_atomic(ticket_id, user_id):
    conn = get_conn()
    try:
        conn.execute("BEGIN IMMEDIATE")
        ticket = conn.execute(
            "SELECT assignment_mode FROM tickets WHERE id=?",(ticket_id,)
        ).fetchone()
        if not ticket or ticket["assignment_mode"] != "Team":
            conn.rollback()
            return False, "This is not a team ticket.", []
        rows = conn.execute("""
            SELECT id,task_name FROM ticket_tasks
            WHERE ticket_id=? AND claimed_by IS NULL
              AND assigned_to IS NULL AND status!='Done'
            ORDER BY id
        """,(ticket_id,)).fetchall()
        if not rows:
            conn.rollback()
            return False, "No available tasks remain.", []
        ids = [r["id"] for r in rows]
        for task_id in ids:
            conn.execute("""
                UPDATE ticket_tasks
                SET claimed_by=?,status='In Progress',assigned_at=?,updated_at=?
                WHERE id=? AND claimed_by IS NULL AND assigned_to IS NULL AND status!='Done'
            """,(user_id,now(),now(),task_id))
        conn.execute(
            "UPDATE tickets SET claimed_by=?,updated_at=? WHERE id=?",
            (user_id,now(),ticket_id)
        )
        conn.commit()
        return True, f"Full ticket taken. {len(ids)} task(s) assigned to you.", ids
    except Exception as e:
        conn.rollback()
        return False, str(e), []
    finally:
        conn.close()

def ticket_task_ownership(ticket_id):
    conn = get_conn()
    rows = conn.execute("""
        SELECT tt.id,tt.task_name,tt.status,
               COALESCE(c.full_name,a.full_name,'Available') AS owner
        FROM ticket_tasks tt
        LEFT JOIN users c ON tt.claimed_by=c.id
        LEFT JOIN users a ON tt.assigned_to=a.id
        WHERE tt.ticket_id=?
        ORDER BY tt.id
    """,(ticket_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ----------------------------- TODAY / FILTERED TASKS -----------------------------
if menu == "Today":
    st.title("Today's Tasks")
    st.markdown('<div class="page-subtitle">Open work due today, overdue work, and today\'s completed tasks</div>', unsafe_allow_html=True)

    today_str = date.today().isoformat()
    conn = get_conn()
    if user["role"] == "Manager":
        rows = conn.execute("""
            SELECT tt.*,t.ticket_no,t.customer_name,t.due_date,
                   a.full_name AS assigned_name,c.full_name AS claimed_name
            FROM ticket_tasks tt
            JOIN tickets t ON tt.ticket_id=t.id
            LEFT JOIN users a ON tt.assigned_to=a.id
            LEFT JOIN users c ON tt.claimed_by=c.id
            ORDER BY t.due_date, tt.id
        """).fetchall()
    else:
        rows = conn.execute("""
            SELECT tt.*,t.ticket_no,t.customer_name,t.due_date,
                   a.full_name AS assigned_name,c.full_name AS claimed_name
            FROM ticket_tasks tt
            JOIN tickets t ON tt.ticket_id=t.id
            LEFT JOIN users a ON tt.assigned_to=a.id
            LEFT JOIN users c ON tt.claimed_by=c.id
            WHERE tt.assigned_to=? OR tt.claimed_by=?
            ORDER BY t.due_date, tt.id
        """,(user["id"],user["id"])).fetchall()
    conn.close()
    rows = [dict(r) for r in rows]

    my_open = [r for r in rows if r["status"] != "Done"]
    due_today = [r for r in my_open if r.get("due_date") == today_str]
    overdue = [r for r in my_open if r.get("due_date") and r["due_date"] < today_str]
    completed_today = [r for r in rows if r["status"] == "Done" and (r.get("updated_at") or "").startswith(today_str)]

    tab1,tab2,tab3 = st.tabs(["Due Today","Overdue","Completed Today"])
    for tab, data, empty_msg in [
        (tab1,due_today,"No tasks due today."),
        (tab2,overdue,"No overdue tasks."),
        (tab3,completed_today,"No tasks completed today.")
    ]:
        with tab:
            if not data:
                st.info(empty_msg)
            for r in data:
                owner = r.get("claimed_name") or r.get("assigned_name") or "Open"
                st.markdown(f"""
                <div class="task-box">
                  <b>{r['ticket_no']} • {r['customer_name']}</b><br>
                  {r['task_name']}<br>
                  <span class="small-muted">Status: {r['status']} • Handled By: {owner} • Due: {r.get('due_date') or '-'}</span>
                </div>
                """, unsafe_allow_html=True)


@st.fragment(run_every="5s")
def live_team_assignment_board():
    st.subheader("Live Team Assignment Board")
    st.caption("Auto-refreshes every 5 seconds")
    conn = get_conn()
    rows = conn.execute("""
        SELECT t.ticket_no,t.customer_name,tt.task_name,tt.status,
               COALESCE(c.full_name,a.full_name,'Available') AS owner,
               t.priority,t.due_date
        FROM ticket_tasks tt
        JOIN tickets t ON t.id=tt.ticket_id
        LEFT JOIN users c ON tt.claimed_by=c.id
        LEFT JOIN users a ON tt.assigned_to=a.id
        WHERE t.overall_status!='Completed'
        ORDER BY
            CASE t.priority WHEN 'Urgent' THEN 1 WHEN 'High' THEN 2
                 WHEN 'Medium' THEN 3 ELSE 4 END,
            t.id DESC,tt.id
    """).fetchall()
    conn.close()
    if not rows:
        st.info("No active task assignments.")
        return
    board = pd.DataFrame([dict(r) for r in rows])
    board.columns = ["Ticket No.","Customer","Bank / Task","Status","Handled By","Priority","Due Date"]
    st.dataframe(board,use_container_width=True,hide_index=True)

# ----------------------------- MANAGER: DASHBOARD -----------------------------
if user["role"] == "Manager" and menu == "Dashboard":
    st.title("Manager Dashboard")
    st.markdown('<div class="page-subtitle">Live overview of office tickets and workload</div>', unsafe_allow_html=True)

    df = get_ticket_df()
    total = len(df)
    open_count = int((df["overall_status"]=="Open").sum()) if not df.empty else 0
    prog_count = int((df["overall_status"]=="In Progress").sum()) if not df.empty else 0
    done_count = int((df["overall_status"]=="Completed").sum()) if not df.empty else 0
    today = date.today().isoformat()
    overdue = int(((df["due_date"].fillna("") < today) &
                   (df["due_date"].fillna("") != "") &
                   (df["overall_status"] != "Completed")).sum()) if not df.empty else 0
    render_kpis([
        ("Total Tickets", total),
        ("Open", open_count),
        ("In Progress", prog_count),
        ("Completed", done_count),
        ("Overdue", overdue),
    ])

    st.subheader("Employee Workload")
    conn = get_conn()
    workload_rows = conn.execute("""
        SELECT
            u.full_name,
            SUM(CASE WHEN tt.status!='Done' AND (tt.assigned_to=u.id OR tt.claimed_by=u.id) THEN 1 ELSE 0 END) AS open_tasks,
            SUM(CASE WHEN tt.status='In Progress' AND (tt.assigned_to=u.id OR tt.claimed_by=u.id) THEN 1 ELSE 0 END) AS in_progress,
            SUM(CASE WHEN tt.status='Done' AND DATE(tt.updated_at)=DATE('now','localtime') AND (tt.assigned_to=u.id OR tt.claimed_by=u.id) THEN 1 ELSE 0 END) AS completed_today
        FROM users u
        LEFT JOIN ticket_tasks tt ON (tt.assigned_to=u.id OR tt.claimed_by=u.id)
        WHERE u.role='Employee' AND u.active=1
        GROUP BY u.id,u.full_name
        ORDER BY open_tasks DESC,u.full_name
    """).fetchall()
    conn.close()
    if workload_rows:
        st.dataframe(pd.DataFrame([dict(r) for r in workload_rows]), use_container_width=True, hide_index=True)

    live_team_assignment_board()

    st.subheader("Recent Tickets")
    if df.empty:
        st.info("No tickets created yet.")
    else:
        for _,r in df.head(10).iterrows():
            render_ticket_card(r.to_dict())

# ----------------------------- MANAGER: RAISE TICKET -----------------------------
elif user["role"] == "Manager" and menu == "Raise Ticket":
    st.title("Raise New Ticket")
    st.markdown('<div class="page-subtitle">Assign directly to one employee or publish to the whole team</div>', unsafe_allow_html=True)

    emps = employees()
    emp_map = {e["full_name"]: e["id"] for e in emps}

    with st.form("raise_ticket"):
        c1,c2 = st.columns(2)
        with c1:
            customer = st.text_input("Customer / Company Name *")
            loan_type = st.selectbox("Loan Type", ["USL","LAP","HL","Used Car","Other"])
            surrogate = st.selectbox("Surrogate", ["Banking","GST","Financial","Other"])
        with c2:
            mode = st.selectbox("Assign Ticket To", ["Individual Employee","Whole Team"])
            selected_emp = None
            if mode == "Individual Employee":
                selected_emp = st.selectbox("Employee *", list(emp_map.keys()) if emp_map else ["No active employees"])
            priority = st.selectbox("Priority", ["Urgent","High","Medium","Normal"])
            due = st.date_input("Due Date")

        remarks = st.text_area("Manager Remarks", placeholder="Case instructions, document notes, special points...")
        st.markdown("#### Initial Tasks")
        task_text = st.text_area(
            "Add one task per line *",
            placeholder="Example:\nLogin in HDFC Bank\nLogin in Tata Capital\nCheck GST documents"
        )

        submit = st.form_submit_button("Create Ticket", type="primary", use_container_width=True)

    if submit:
        task_lines = [x.strip() for x in task_text.splitlines() if x.strip()]
        valid, msg = validate_text_fields(
            customer=customer,
            manager_remarks=remarks,
            tasks=" ".join(task_lines)
        )
        if not valid:
            st.error(msg)
        elif not customer.strip():
            st.error("Customer / Company Name is required.")
        elif not task_lines:
            st.error("Add at least one task.")
        elif mode == "Individual Employee" and not emp_map:
            st.error("Create an employee first.")
        else:
            assigned_to = emp_map.get(selected_emp) if mode == "Individual Employee" else None
            assignment_mode = "Individual" if mode == "Individual Employee" else "Team"
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tickets(
                    customer_name,loan_type,surrogate,assignment_mode,assigned_to,
                    priority,due_date,manager_remarks,overall_status,created_by,created_at,updated_at
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                customer.strip(),loan_type,surrogate,assignment_mode,assigned_to,
                priority,due.isoformat(),remarks.strip(),"Open",user["id"],now(),now()
            ))
            ticket_id = cur.lastrowid
            ticket_no = f"GFS-{ticket_id:05d}"
            cur.execute("UPDATE tickets SET ticket_no=? WHERE id=?", (ticket_no,ticket_id))
            for task_name in task_lines:
                cur.execute("""
                    INSERT INTO ticket_tasks(
                        ticket_id,task_name,status,assigned_to,created_by,created_at,updated_at
                    ) VALUES (?,?,?,?,?,?,?)
                """, (
                    ticket_id,task_name,"Open",
                    assigned_to if assignment_mode=="Individual" else None,
                    user["id"],now(),now()
                ))
            conn.commit()
            conn.close()
            add_activity(ticket_id,user["id"],f"Ticket created ({assignment_mode}) with {len(task_lines)} task(s)")
            if assignment_mode == "Individual":
                notify_user(assigned_to, f"New ticket assigned: {ticket_no} - {customer.strip()}", ticket_id=ticket_id)
            else:
                notify_all_active_employees(f"New team ticket available: {ticket_no} - {customer.strip()}", ticket_id=ticket_id)
            st.success(f"{ticket_no} created successfully.")

# ----------------------------- MANAGER: ALL TICKETS -----------------------------
elif user["role"] == "Manager" and menu == "All Tickets":
    st.title("All Tickets")
    st.markdown('<div class="page-subtitle">Review, add tasks, and manage ticket progress</div>', unsafe_allow_html=True)

    df = get_ticket_df()
    if df.empty:
        st.info("No tickets available.")
    else:
        c1,c2,c3,c4 = st.columns(4)
        with c1:
            sf = st.selectbox("Status", ["All","Open","In Progress","Completed"])
        with c2:
            mf = st.selectbox("Assignment", ["All","Individual","Team"])
        with c3:
            employee_filter = st.selectbox("Employee", ["All"] + [e["full_name"] for e in employees()])
        with c4:
            search = st.text_input("Search customer / ticket / lender / task")

        f = df.copy()
        if sf != "All":
            f = f[f["overall_status"]==sf]
        if mf != "All":
            f = f[f["assignment_mode"]==mf]
        if employee_filter != "All":
            f = f[
                (f["assigned_name"].fillna("") == employee_filter) |
                (f["claimed_name"].fillna("") == employee_filter)
            ]
        if search.strip():
            q = search.lower().strip()
            conn = get_conn()
            matching_ticket_ids = [
                r["ticket_id"] for r in conn.execute("""
                    SELECT DISTINCT ticket_id
                    FROM ticket_tasks
                    WHERE LOWER(task_name) LIKE ? OR LOWER(COALESCE(details,'')) LIKE ? OR LOWER(COALESCE(lender_name,'')) LIKE ?
                """,(f"%{q}%",f"%{q}%",f"%{q}%")).fetchall()
            ]
            conn.close()
            f = f[
                f["customer_name"].str.lower().str.contains(q,na=False) |
                f["ticket_no"].str.lower().str.contains(q,na=False) |
                f["id"].isin(matching_ticket_ids)
            ]

        for _,r in f.iterrows():
            row = r.to_dict()
            render_ticket_card(row)
            copy_ticket_button(row["ticket_no"], f"copy_mgr_{row['id']}")
            with st.expander(f"Manage {row['ticket_no']} — {row['customer_name']}"):
                st.write("**Manager Remarks:**", row.get("manager_remarks") or "-")
                if row["assignment_mode"] == "Team":
                    st.write("**Ticket Owner:**", row.get("claimed_name") or "Not yet claimed")
                else:
                    st.write("**Assigned Employee:**", row.get("assigned_name") or "-")

                st.markdown("#### Add New Task")
                emps_now = employees()
                emp_names_now = [e["full_name"] for e in emps_now]
                emp_lookup_now = {e["full_name"]: e["id"] for e in emps_now}
                with st.form(f"add_task_{row['id']}"):
                    tname = st.text_input("Task Name", key=f"tn_{row['id']}")
                    tdetails = st.text_input("Task Details / Lender (optional)", key=f"td_{row['id']}")
                    assignment = st.selectbox(
                        "Task Assignment",
                        ["Same as ticket","Open to whole team","Specific employee"],
                        key=f"ta_{row['id']}"
                    )
                    chosen_task_emp = None
                    if assignment == "Specific employee":
                        chosen_task_emp = st.selectbox("Assign task to", emp_names_now, key=f"tep_{row['id']}")
                    add = st.form_submit_button("Add Task")
                if add and tname.strip():
                    valid,msg = validate_text_fields(task_name=tname, task_details=tdetails)
                    if not valid:
                        st.error(msg)
                    else:
                        if assignment == "Same as ticket" and row["assignment_mode"]=="Individual":
                            assigned_to = row["assigned_to"]
                        elif assignment == "Specific employee":
                            assigned_to = emp_lookup_now.get(chosen_task_emp)
                        else:
                            assigned_to = None
                        conn = get_conn()
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO ticket_tasks(
                                ticket_id,task_name,details,status,assigned_to,created_by,created_at,updated_at,assigned_at
                            ) VALUES (?,?,?,?,?,?,?,?,?)
                        """, (row["id"],tname.strip(),tdetails.strip(),"Open",assigned_to,user["id"],now(),now(),now() if assigned_to else None))
                        task_id = cur.lastrowid
                        conn.commit()
                        conn.close()
                        add_activity(row["id"],user["id"],f"New task added: {tname.strip()}",task_id)
                        if assigned_to:
                            notify_user(assigned_to, f"New task assigned in {row['ticket_no']}: {tname.strip()}", row["id"], task_id)
                        else:
                            notify_all_active_employees(f"New open task in {row['ticket_no']}: {tname.strip()}", row["id"], task_id)
                        recalc_ticket(row["id"])
                        st.success("Task added.")
                        st.rerun()

                st.markdown("#### Comments")
                for c in comments_for(row["id"]):
                    st.markdown(f"**{c['full_name']}** · {c['created_at']}")
                    st.write(c["comment_text"])
                if user["role"] == "Employee":
                    with st.form(f"poolcomment_{row['id']}"):
                        ctext = st.text_input("Add comment", key=f"pct_{row['id']}")
                        csubmit = st.form_submit_button("Post")
                    if csubmit and ctext.strip():
                        valid,msg = validate_text_fields(comment=ctext)
                        if not valid:
                            st.error(msg)
                        else:
                            conn = get_conn()
                            conn.execute(
                                "INSERT INTO comments(ticket_id,user_id,comment_text,created_at) VALUES (?,?,?,?)",
                                (row["id"],user["id"],ctext.strip(),now())
                            )
                            conn.commit()
                            conn.close()
                            st.rerun()

                st.markdown("#### Tasks")
                tasks = tasks_for(row["id"])
                for t in tasks:
                    owner = t.get("claimed_name") or t.get("assigned_name") or "Open to team"
                    st.markdown(f"""
                    <div class="task-box">
                      <b>{t['task_name']}</b><br>
                      <span class="small-muted">Status: {t['status']} &nbsp; • &nbsp; Handled By: {owner}</span>
                    </div>
                    """, unsafe_allow_html=True)
                    cc1,cc2 = st.columns([2,1])
                    with cc1:
                        statuses = ["Open","In Progress","Waiting for Customer","Documents Required","Rejected","Rework","Done"]
                        idx = statuses.index(t["status"]) if t["status"] in statuses else 0
                        new_status = st.selectbox("Manager status", statuses, index=idx, key=f"mstatus_{t['id']}")
                    with cc2:
                        if st.button("Save", key=f"msave_{t['id']}"):
                            conn = get_conn()
                            conn.execute(
                                "UPDATE ticket_tasks SET status=?,updated_at=? WHERE id=?",
                                (new_status,now(),t["id"])
                            )
                            conn.commit()
                            conn.close()
                            add_activity(row["id"],user["id"],f"Task '{t['task_name']}' changed to {new_status}",t["id"])
                            recalc_ticket(row["id"])
                            st.rerun()

                    # Reassign task
                    active_emps = employees()
                    reassignment_options = ["Open to whole team"] + [e["full_name"] for e in active_emps]
                    reassign_to = st.selectbox("Reassign task", reassignment_options, key=f"reas_{t['id']}")
                    if st.button("Apply Reassignment", key=f"reab_{t['id']}"):
                        new_assigned = None
                        if reassign_to != "Open to whole team":
                            new_assigned = next((e["id"] for e in active_emps if e["full_name"] == reassign_to), None)
                        conn = get_conn()
                        conn.execute(
                            "UPDATE ticket_tasks SET assigned_to=?, claimed_by=NULL, status='Open', assigned_at=?, updated_at=? WHERE id=?",
                            (new_assigned, now() if new_assigned else None, now(), t["id"])
                        )
                        conn.commit()
                        conn.close()
                        add_activity(row["id"],user["id"],f"Task reassigned: {t['task_name']}",t["id"])
                        if new_assigned:
                            notify_user(new_assigned, f"Task reassigned to you in {row['ticket_no']}: {t['task_name']}", row["id"], t["id"])
                        else:
                            notify_all_active_employees(f"Task reopened to team in {row['ticket_no']}: {t['task_name']}", row["id"], t["id"])
                        st.success("Task reassigned.")
                        st.rerun()

                st.markdown("#### Comments")
                with st.form(f"comment_{row['id']}"):
                    comment_text = st.text_input("Add comment", key=f"ct_{row['id']}")
                    add_comment = st.form_submit_button("Post Comment")
                if add_comment and comment_text.strip():
                    valid,msg = validate_text_fields(comment=comment_text)
                    if not valid:
                        st.error(msg)
                    else:
                        conn = get_conn()
                        conn.execute(
                            "INSERT INTO comments(ticket_id,user_id,comment_text,created_at) VALUES (?,?,?,?)",
                            (row["id"],user["id"],comment_text.strip(),now())
                        )
                        conn.commit()
                        conn.close()
                        notify_all_active_employees(
                            f"New comment on {row['ticket_no']}: {comment_text.strip()[:80]}",
                            ticket_id=row["id"],
                            exclude_user_id=user["id"]
                        )
                        st.rerun()

                for c in comments_for(row["id"]):
                    st.markdown(f"**{c['full_name']}** · {c['created_at']}")
                    st.write(c["comment_text"])

                st.markdown("#### Activity")
                conn = get_conn()
                logs = conn.execute("""
                    SELECT al.created_at,u.full_name,al.action
                    FROM activity_log al
                    LEFT JOIN users u ON al.user_id=u.id
                    WHERE al.ticket_id=?
                    ORDER BY al.id DESC
                    LIMIT 30
                """,(row["id"],)).fetchall()
                conn.close()
                if logs:
                    st.dataframe(pd.DataFrame([dict(x) for x in logs]), use_container_width=True, hide_index=True)

# ----------------------------- TEAM POOL -----------------------------
elif menu == "Team Pool":
    st.title("Team Pool")
    st.markdown(
        '<div class="page-subtitle">Take the whole ticket or choose only the banks/tasks you can handle</div>',
        unsafe_allow_html=True
    )

    df = get_ticket_df("t.assignment_mode='Team'")
    team_filter = st.selectbox("Quick Filter", ["All Team Tickets","Open Team Tickets","Completed Today"])
    if team_filter == "Open Team Tickets" and not df.empty:
        df = df[df["overall_status"] != "Completed"]
    elif team_filter == "Completed Today" and not df.empty:
        today_str = date.today().isoformat()
        df = df[df["updated_at"].fillna("").str.startswith(today_str)]

    if df.empty:
        st.info("No team tickets available.")
    else:
        for _,r in df.iterrows():
            row = r.to_dict()
            render_ticket_card(row)
            copy_ticket_button(row["ticket_no"], f"copy_pool_{row['id']}")

            with st.expander(f"{row['ticket_no']} — {row['customer_name']}"):
                st.write("**Manager Remarks:**", row.get("manager_remarks") or "-")

                tasks = tasks_for(row["id"])
                available = [
                    t for t in tasks
                    if not t.get("claimed_by")
                    and not t.get("assigned_to")
                    and t["status"] != "Done"
                ]

                if user["role"] == "Employee" and available:
                    st.markdown("### Take Work")
                    c1,c2 = st.columns(2)

                    with c1:
                        st.markdown("**Take Full Ticket**")
                        st.caption("Assign every currently available bank/task to yourself.")
                        if st.button(
                            "Take Full Ticket",
                            key=f"full_{row['id']}",
                            type="primary",
                            use_container_width=True
                        ):
                            ok,msg,ids = claim_full_ticket_atomic(row["id"],user["id"])
                            if ok:
                                for task_id in ids:
                                    t = next((x for x in tasks if x["id"] == task_id),None)
                                    if t:
                                        add_activity(row["id"],user["id"],f"Task claimed: {t['task_name']}",task_id)
                                notify_all_active_employees(
                                    f"{row['ticket_no']} available work taken by {user['full_name']}",
                                    ticket_id=row["id"],exclude_user_id=user["id"]
                                )
                                recalc_ticket(row["id"])
                                st.success(msg)
                                st.rerun()
                            else:
                                st.warning(msg)

                    with c2:
                        st.markdown("**Take Selected Banks / Tasks**")
                        st.caption("Select only the items you can handle. Others stay available.")

                    selected = []
                    for t in available:
                        if st.checkbox(t["task_name"],key=f"pick_{row['id']}_{t['id']}"):
                            selected.append(t["id"])

                    if st.button(
                        "Take Selected Tasks",
                        key=f"partial_{row['id']}",
                        disabled=not selected,
                        use_container_width=True
                    ):
                        ok,msg = claim_selected_tasks_atomic(row["id"],selected,user["id"])
                        if ok:
                            names = []
                            for task_id in selected:
                                t = next((x for x in tasks if x["id"] == task_id),None)
                                if t:
                                    names.append(t["task_name"])
                                    add_activity(row["id"],user["id"],f"Task claimed: {t['task_name']}",task_id)
                            notify_all_active_employees(
                                f"{user['full_name']} took {', '.join(names)} in {row['ticket_no']}",
                                ticket_id=row["id"],exclude_user_id=user["id"]
                            )
                            recalc_ticket(row["id"])
                            st.success(msg)
                            st.rerun()
                        else:
                            st.warning(msg)

                st.markdown("### Bank / Task Allocation")
                for t in tasks_for(row["id"]):
                    owner = t.get("claimed_name") or t.get("assigned_name") or "Available"
                    badge = (
                        f'<span class="badge b-claimed">Handled by: {owner}</span>'
                        if owner != "Available"
                        else '<span class="badge b-open">Available</span>'
                    )
                    st.markdown(f"""
                    <div class="task-box">
                      <b>{t['task_name']}</b><br>
                      <span class="small-muted">Status: {t['status']}</span><br>
                      {badge}
                    </div>
                    """,unsafe_allow_html=True)

                    is_mine = (
                        user["role"] == "Employee"
                        and (t.get("claimed_by") == user["id"] or t.get("assigned_to") == user["id"])
                    )
                    if is_mine:
                        with st.form(f"upd_{t['id']}"):
                            statuses = [
                                "In Progress","Waiting for Customer","Documents Required",
                                "Rejected","Rework","Done"
                            ]
                            idx = statuses.index(t["status"]) if t["status"] in statuses else 0
                            ns = st.selectbox("Status",statuses,index=idx,key=f"s_{t['id']}")
                            login_id = st.text_input(
                                "Login / Application ID",
                                value=t.get("login_id") or "",
                                key=f"l_{t['id']}"
                            )
                            remark = st.text_area(
                                "Remark",
                                value=t.get("employee_remark") or "",
                                key=f"r_{t['id']}"
                            )
                            save = st.form_submit_button("Save Update")
                        if save:
                            valid,msg = validate_text_fields(remark=remark,login_id=login_id)
                            if not valid:
                                st.error(msg)
                            else:
                                conn = get_conn()
                                conn.execute("""
                                    UPDATE ticket_tasks
                                    SET status=?,login_id=?,employee_remark=?,updated_at=?
                                    WHERE id=?
                                """,(ns,login_id.strip(),remark.strip(),now(),t["id"]))
                                conn.commit()
                                conn.close()
                                add_activity(
                                    row["id"],user["id"],
                                    f"Task '{t['task_name']}' updated to {ns}",
                                    t["id"]
                                )
                                recalc_ticket(row["id"])
                                st.rerun()

                st.markdown("### Comments")
                for c in comments_for(row["id"]):
                    st.markdown(f"**{c['full_name']}** · {c['created_at']}")
                    st.write(c["comment_text"])

                if user["role"] == "Employee":
                    with st.form(f"comment_{row['id']}"):
                        text = st.text_input("Add comment",key=f"c_{row['id']}")
                        post = st.form_submit_button("Post")
                    if post and text.strip():
                        valid,msg = validate_text_fields(comment=text)
                        if not valid:
                            st.error(msg)
                        else:
                            conn = get_conn()
                            conn.execute(
                                "INSERT INTO comments(ticket_id,user_id,comment_text,created_at) VALUES (?,?,?,?)",
                                (row["id"],user["id"],text.strip(),now())
                            )
                            conn.commit()
                            conn.close()
                            st.rerun()

# ----------------------------- MANAGER: EMPLOYEES -----------------------------
elif user["role"] == "Manager" and menu == "Employees":
    st.title("Employee Management")
    st.markdown('<div class="page-subtitle">Only managers can create, reset or deactivate employee accounts</div>', unsafe_allow_html=True)

    tab1,tab2 = st.tabs(["Employee List","Create Employee"])

    with tab1:
        rows = employees(active_only=False)
        if not rows:
            st.info("No employee accounts yet.")
        else:
            for e in rows:
                status = "Active" if e["active"] else "Inactive"
                with st.expander(f"{e['full_name']} — @{e['username']} — {status}"):
                    c1,c2 = st.columns(2)
                    with c1:
                        new_name = st.text_input("Full Name",value=e["full_name"],key=f"en_{e['id']}")
                        new_username = st.text_input("Username",value=e["username"],key=f"eu_{e['id']}")
                        if st.button("Save Name / Username",key=f"esave_{e['id']}"):
                            valid,msg = validate_text_fields(full_name=new_name, username=new_username)
                            if not valid:
                                st.error(msg)
                            else:
                                try:
                                    conn = get_conn()
                                    conn.execute(
                                        "UPDATE users SET full_name=?,username=? WHERE id=?",
                                        (new_name.strip(),new_username.strip(),e["id"])
                                    )
                                    conn.commit()
                                    conn.close()
                                    st.success("Employee updated.")
                                    st.rerun()
                                except sqlite3.IntegrityError:
                                    st.error("Username already exists.")
                    with c2:
                        new_password = st.text_input("Reset Password",type="password",key=f"ep_{e['id']}")
                        if st.button("Reset Password",key=f"erp_{e['id']}"):
                            if len(new_password) < 4:
                                st.error("Use at least 4 characters.")
                            else:
                                salt,pwd_hash = hash_password(new_password)
                                conn = get_conn()
                                conn.execute(
                                    "UPDATE users SET password_salt=?,password_hash=? WHERE id=?",
                                    (salt,pwd_hash,e["id"])
                                )
                                conn.commit()
                                conn.close()
                                st.success("Password reset successfully.")
                        new_active = st.toggle("Active Account", value=bool(e["active"]), key=f"ea_{e['id']}")
                        if st.button("Save Account Status",key=f"east_{e['id']}"):
                            conn = get_conn()
                            conn.execute("UPDATE users SET active=? WHERE id=?",(1 if new_active else 0,e["id"]))
                            conn.commit()
                            conn.close()
                            st.success("Account status updated.")
                            st.rerun()

    with tab2:
        with st.form("new_employee"):
            full_name = st.text_input("Employee Name *")
            username = st.text_input("Username *")
            password = st.text_input("Password *",type="password")
            create = st.form_submit_button("Create Employee",type="primary")
        if create:
            valid,msg = validate_text_fields(full_name=full_name, username=username)
            if not valid:
                st.error(msg)
            elif not full_name.strip() or not username.strip() or len(password)<4:
                st.error("Enter name, username and password (minimum 4 characters).")
            else:
                try:
                    salt,pwd_hash = hash_password(password)
                    conn = get_conn()
                    conn.execute("""
                        INSERT INTO users(username,password_salt,password_hash,full_name,role,active,created_at)
                        VALUES (?,?,?,?,?,?,?)
                    """,(username.strip(),salt,pwd_hash,full_name.strip(),"Employee",1,now()))
                    conn.commit()
                    conn.close()
                    st.success("Employee account created.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("Username already exists.")


# ----------------------------- NOTIFICATIONS -----------------------------
elif menu == "Notifications":
    st.title("Notifications")
    st.markdown('<div class="page-subtitle">New assignments, claims, comments and team updates</div>', unsafe_allow_html=True)

    conn = get_conn()
    rows = conn.execute("""
        SELECT *
        FROM notifications
        WHERE user_id=?
        ORDER BY id DESC
        LIMIT 100
    """,(user["id"],)).fetchall()
    conn.close()

    if st.button("Mark all as read"):
        conn = get_conn()
        conn.execute("UPDATE notifications SET is_read=1 WHERE user_id=?",(user["id"],))
        conn.commit()
        conn.close()
        st.rerun()

    if not rows:
        st.info("No notifications.")
    else:
        for n in rows:
            prefix = "NEW" if not n["is_read"] else "READ"
            st.markdown(f"**{prefix}** · {n['created_at']}")
            st.write(n["message"])
            st.divider()

# ----------------------------- MANAGER: REPORTS -----------------------------
elif user["role"] == "Manager" and menu == "Reports":
    st.title("Reports")
    st.markdown('<div class="page-subtitle">Export ticket and task status for office review</div>', unsafe_allow_html=True)
    df = get_ticket_df()
    if df.empty:
        st.info("No data available.")
    else:
        st.dataframe(df[[
            "ticket_no","customer_name","loan_type","surrogate","assignment_mode",
            "assigned_name","claimed_name","priority","due_date","overall_status","created_at","updated_at"
        ]],use_container_width=True,hide_index=True)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("Download Ticket Report CSV",csv,"office_ticket_report.csv","text/csv",use_container_width=True)

# ----------------------------- EMPLOYEE: DASHBOARD -----------------------------
elif user["role"] == "Employee" and menu == "My Dashboard":
    st.title("My Dashboard")
    st.markdown('<div class="page-subtitle">Your assigned and claimed work</div>', unsafe_allow_html=True)

    df = get_ticket_df(
        "(t.assigned_to=? OR t.claimed_by=?)",
        (user["id"],user["id"])
    )
    total = len(df)
    open_count = int((df["overall_status"]=="Open").sum()) if not df.empty else 0
    prog = int((df["overall_status"]=="In Progress").sum()) if not df.empty else 0
    done = int((df["overall_status"]=="Completed").sum()) if not df.empty else 0

    # count tasks owned by user
    conn = get_conn()
    my_tasks = conn.execute("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN status='Done' THEN 1 ELSE 0 END) AS done
        FROM ticket_tasks
        WHERE assigned_to=? OR claimed_by=?
    """,(user["id"],user["id"])).fetchone()
    conn.close()

    render_kpis([
        ("My Tickets",total),
        ("Open",open_count),
        ("In Progress",prog),
        ("Completed",done),
        ("My Tasks",my_tasks["total"] or 0),
    ])

    if df.empty:
        st.info("No tickets assigned or claimed yet.")
    else:
        for _,r in df.head(10).iterrows():
            render_ticket_card(r.to_dict())

# ----------------------------- EMPLOYEE: MY TICKETS -----------------------------
elif user["role"] == "Employee" and menu == "My Tickets":
    st.title("My Tickets")
    st.markdown('<div class="page-subtitle">Update only work assigned to you or claimed by you</div>', unsafe_allow_html=True)

    df = get_ticket_df(
        "(t.assigned_to=? OR t.claimed_by=?)",
        (user["id"],user["id"])
    )
    quick_filter = st.selectbox("Quick Filter", ["All","My Open Tasks","Completed Today"])
    if quick_filter == "My Open Tasks" and not df.empty:
        df = df[df["overall_status"] != "Completed"]
    elif quick_filter == "Completed Today" and not df.empty:
        today_str = date.today().isoformat()
        df = df[df["updated_at"].fillna("").str.startswith(today_str)]
    if df.empty:
        st.info("No tickets assigned to you.")
    else:
        for _,r in df.iterrows():
            row = r.to_dict()
            render_ticket_card(row)
            copy_ticket_button(row["ticket_no"], f"copy_my_{row['id']}")
            with st.expander(f"Open {row['ticket_no']} — {row['customer_name']}"):
                st.write("**Manager Remarks:**",row.get("manager_remarks") or "-")
                for t in tasks_for(row["id"]):
                    is_mine = t.get("assigned_to")==user["id"] or t.get("claimed_by")==user["id"]
                    st.markdown(f"""
                    <div class="task-box">
                      <b>{t['task_name']}</b><br>
                      <span class="small-muted">Status: {t['status']} &nbsp; • &nbsp; Owner: {t.get('claimed_name') or t.get('assigned_name') or 'Open'}</span>
                    </div>
                    """,unsafe_allow_html=True)
                    if is_mine:
                        with st.form(f"mytask_{t['id']}"):
                            statuses = ["Open","In Progress","Waiting for Customer","Documents Required","Rejected","Rework","Done"]
                            idx = statuses.index(t["status"]) if t["status"] in statuses else 0
                            ns = st.selectbox("Status",statuses,index=idx,key=f"mys_{t['id']}")
                            login_id = st.text_input("Login / Application ID",value=t.get("login_id") or "",key=f"myli_{t['id']}")
                            remark = st.text_area("Remark",value=t.get("employee_remark") or "",key=f"myr_{t['id']}")
                            save = st.form_submit_button("Save")
                        if save:
                            valid,msg = validate_text_fields(remark=remark, login_id=login_id)
                            if not valid:
                                st.error(msg)
                                st.stop()
                            conn = get_conn()
                            conn.execute("""
                                UPDATE ticket_tasks
                                SET status=?,login_id=?,employee_remark=?,updated_at=?
                                WHERE id=?
                            """,(ns,login_id.strip(),remark.strip(),now(),t["id"]))
                            conn.commit()
                            conn.close()
                            add_activity(row["id"],user["id"],f"Task '{t['task_name']}' updated to {ns}",t["id"])
                            recalc_ticket(row["id"])
                            st.rerun()
