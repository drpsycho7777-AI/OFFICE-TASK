
import streamlit as st
import sqlite3
from datetime import datetime, date
from pathlib import Path
import pandas as pd

DB_PATH = Path(__file__).with_name("tickets.db")

st.set_page_config(
    page_title="Office Task Desk",
    page_icon="✅",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- DB ----------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_no TEXT UNIQUE,
            customer_name TEXT NOT NULL,
            loan_type TEXT,
            required_amount REAL,
            surrogate TEXT,
            assigned_to INTEGER,
            priority TEXT,
            due_date TEXT,
            manager_remarks TEXT,
            overall_status TEXT DEFAULT 'Open',
            created_by INTEGER,
            created_at TEXT,
            updated_at TEXT,
            FOREIGN KEY(assigned_to) REFERENCES users(id),
            FOREIGN KEY(created_by) REFERENCES users(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ticket_lenders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER NOT NULL,
            lender_name TEXT NOT NULL,
            status TEXT DEFAULT 'Pending',
            login_id TEXT,
            employee_remark TEXT,
            updated_at TEXT,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            user_id INTEGER,
            action TEXT,
            created_at TEXT,
            FOREIGN KEY(ticket_id) REFERENCES tickets(id),
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
    """)

    # Demo users
    users = [
        ("manager", "1234", "Manager Demo", "Manager"),
        ("rahul", "1234", "Rahul", "Employee"),
        ("priya", "1234", "Priya", "Employee"),
        ("amit", "1234", "Amit", "Employee"),
    ]
    for u in users:
        try:
            cur.execute("INSERT INTO users(username,password,full_name,role) VALUES (?,?,?,?)", u)
        except sqlite3.IntegrityError:
            pass

    conn.commit()
    conn.close()

def add_activity(ticket_id, user_id, action):
    conn = get_conn()
    conn.execute(
        "INSERT INTO activity_log(ticket_id,user_id,action,created_at) VALUES (?,?,?,?)",
        (ticket_id, user_id, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    conn.commit()
    conn.close()

def recalc_ticket(ticket_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT status FROM ticket_lenders WHERE ticket_id=?",
        (ticket_id,)
    ).fetchall()

    statuses = [r["status"] for r in rows]
    if statuses and all(s == "Login Done" for s in statuses):
        overall = "Completed"
    elif statuses and any(s in ("Login Done", "Rejected", "Documents Required", "Re-login / Rework") for s in statuses):
        overall = "In Progress"
    else:
        overall = "Open"

    conn.execute(
        "UPDATE tickets SET overall_status=?, updated_at=? WHERE id=?",
        (overall, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), ticket_id)
    )
    conn.commit()
    conn.close()

init_db()

# ---------- STYLE ----------
st.markdown("""
<style>
/* ---------- Global ---------- */
html, body, [class*="css"] {
    font-family: "Segoe UI", Arial, sans-serif;
}
.block-container {
    padding-top: 1.4rem;
    padding-bottom: 2rem;
    max-width: 1500px;
}
h1 {
    font-size: 2rem !important;
    font-weight: 750 !important;
    letter-spacing: -0.3px;
    margin-bottom: 0.2rem !important;
}
h2, h3 {
    font-weight: 700 !important;
}

/* ---------- Sidebar ---------- */
section[data-testid="stSidebar"] {
    border-right: 1px solid #e5e7eb;
}
section[data-testid="stSidebar"] .block-container {
    padding-top: 1.2rem;
}
section[data-testid="stSidebar"] div[role="radiogroup"] label {
    padding: 0.25rem 0;
}

/* ---------- KPI Cards ---------- */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(5, minmax(120px, 1fr));
    gap: 14px;
    margin: 10px 0 24px 0;
}
.kpi-card {
    background: #ffffff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 16px 18px;
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
.kpi-label {
    color: #6b7280;
    font-size: 0.82rem;
    font-weight: 600;
    margin-bottom: 4px;
}
.kpi-value {
    color: #111827;
    font-size: 1.8rem;
    font-weight: 750;
    line-height: 1.1;
}

/* ---------- Ticket Cards ---------- */
.ticket-card {
    border: 1px solid #e5e7eb;
    border-left: 4px solid #2563eb;
    border-radius: 14px;
    padding: 16px 18px;
    margin-bottom: 12px;
    background: #ffffff;
    box-shadow: 0 2px 8px rgba(15,23,42,0.04);
}
.ticket-title {
    font-size: 1.02rem;
    font-weight: 750;
    color: #111827;
    margin-bottom: 7px;
}
.small-muted {
    color: #6b7280;
    font-size: 0.88rem;
}
.badge {
    display: inline-block;
    padding: 4px 9px;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    margin-right: 5px;
}
.badge-open { background:#eff6ff; color:#1d4ed8; }
.badge-progress { background:#fff7ed; color:#c2410c; }
.badge-completed { background:#ecfdf5; color:#047857; }
.badge-high { background:#fef2f2; color:#b91c1c; }
.badge-medium { background:#fffbeb; color:#b45309; }
.badge-normal { background:#f3f4f6; color:#4b5563; }

/* ---------- Header ---------- */
.page-subtitle {
    color: #6b7280;
    margin-top: -2px;
    margin-bottom: 16px;
    font-size: 0.92rem;
}
.brand-box {
    padding: 4px 0 10px 0;
}
.brand-title {
    font-size: 1.15rem;
    font-weight: 800;
    color: #111827;
}
.brand-subtitle {
    font-size: 0.78rem;
    color: #6b7280;
}

/* ---------- Buttons ---------- */
.stButton > button {
    border-radius: 10px;
    font-weight: 650;
}
.stDownloadButton > button {
    border-radius: 10px;
    font-weight: 650;
}

/* ---------- Inputs ---------- */
div[data-baseweb="input"] > div,
div[data-baseweb="select"] > div,
textarea {
    border-radius: 10px !important;
}

/* ---------- Mobile ---------- */
@media (max-width: 900px) {
    .kpi-grid {
        grid-template-columns: repeat(2, minmax(120px, 1fr));
    }
}
</style>
""", unsafe_allow_html=True)

# ---------- SESSION ----------
if "user" not in st.session_state:
    st.session_state.user = None

def login_screen():
    st.title("Office Task Desk")
    st.markdown('<div class="page-subtitle">Simple internal task & ticket tracking for your office</div>', unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1,1.2,1])
    with c2:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login", use_container_width=True, type="primary"):
            conn = get_conn()
            user = conn.execute(
                "SELECT * FROM users WHERE username=? AND password=?",
                (username.strip(), password.strip())
            ).fetchone()
            conn.close()
            if user:
                st.session_state.user = dict(user)
                st.rerun()
            else:
                st.error("Invalid username or password")

        st.info(
            "Online demo logins:\n\n"
            "Manager: **manager / 1234**\n\n"
            "Employee: **rahul / 1234** or **priya / 1234**"
        )

if not st.session_state.user:
    login_screen()
    st.stop()

user = st.session_state.user

# ---------- SIDEBAR ----------
st.sidebar.markdown("""
<div class="brand-box">
    <div class="brand-title">✅ Office Task Desk</div>
    <div class="brand-subtitle">Task & Login Tracker</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.write(f"**{user['full_name']}**")
st.sidebar.caption(user["role"])

if user["role"] == "Manager":
    menu = st.sidebar.radio(
        "Menu",
        ["Dashboard", "Raise Ticket", "All Tickets", "Reports"]
    )
else:
    menu = st.sidebar.radio(
        "Menu",
        ["My Dashboard", "My Tickets"]
    )

if st.sidebar.button("Logout"):
    st.session_state.user = None
    st.rerun()

# ---------- HELPERS ----------
def employees():
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, full_name FROM users WHERE role='Employee' ORDER BY full_name"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def ticket_df(where="", params=()):
    conn = get_conn()
    q = """
        SELECT t.*, u.full_name AS assigned_name, c.full_name AS created_name
        FROM tickets t
        LEFT JOIN users u ON t.assigned_to=u.id
        LEFT JOIN users c ON t.created_by=c.id
    """
    if where:
        q += " WHERE " + where
    q += " ORDER BY t.id DESC"
    rows = conn.execute(q, params).fetchall()
    conn.close()
    return pd.DataFrame([dict(r) for r in rows])

def lenders_for(ticket_id):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM ticket_lenders WHERE ticket_id=? ORDER BY id",
        (ticket_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]

def render_ticket_summary(row):
    due = row.get("due_date") or "-"
    amount = row.get("required_amount")
    amount_txt = f"₹{amount:,.0f}" if amount else "-"
    status = row.get("overall_status","Open")
    priority = row.get("priority","Normal")
    status_class = {
        "Open": "badge-open",
        "In Progress": "badge-progress",
        "Completed": "badge-completed",
    }.get(status, "badge-open")
    priority_class = {
        "High": "badge-high",
        "Medium": "badge-medium",
        "Normal": "badge-normal",
    }.get(priority, "badge-normal")

    st.markdown(f"""
    <div class="ticket-card">
        <div class="ticket-title">{row['ticket_no']} &nbsp;•&nbsp; {row['customer_name']}</div>
        <div class="small-muted">
            👤 {row.get('assigned_name','-')} &nbsp;&nbsp; • &nbsp;&nbsp;
            💼 {row.get('loan_type','-')} &nbsp;&nbsp; • &nbsp;&nbsp;
            💰 {amount_txt} &nbsp;&nbsp; • &nbsp;&nbsp;
            📅 {due}
        </div>
        <div style="margin-top:10px">
            <span class="badge {priority_class}">{priority}</span>
            <span class="badge {status_class}">{status}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_kpis(items):
    cards = "".join(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div><div class="kpi-value">{value}</div></div>'
        for label, value in items
    )
    st.markdown(f'<div class="kpi-grid">{cards}</div>', unsafe_allow_html=True)

# ---------- MANAGER DASHBOARD ----------
if user["role"] == "Manager" and menu == "Dashboard":
    st.title("Manager Dashboard")

    df = ticket_df()
    total = len(df)
    open_count = int((df["overall_status"] == "Open").sum()) if not df.empty else 0
    in_prog = int((df["overall_status"] == "In Progress").sum()) if not df.empty else 0
    completed = int((df["overall_status"] == "Completed").sum()) if not df.empty else 0

    today = date.today().isoformat()
    overdue = 0
    if not df.empty:
        overdue = int(((df["due_date"].fillna("") < today) &
                       (df["due_date"].fillna("") != "") &
                       (df["overall_status"] != "Completed")).sum())

    st.markdown('<div class="page-subtitle">Quick overview of all assigned office tasks</div>', unsafe_allow_html=True)
    render_kpis([
        ("Total Tickets", total),
        ("Open", open_count),
        ("In Progress", in_prog),
        ("Completed", completed),
        ("Overdue", overdue),
    ])

    st.subheader("Recent Tickets")
    if df.empty:
        st.info("No tickets yet.")
    else:
        for _, row in df.head(8).iterrows():
            render_ticket_summary(row.to_dict())

# ---------- RAISE TICKET ----------
elif user["role"] == "Manager" and menu == "Raise Ticket":
    st.title("Raise New Ticket")
    st.markdown('<div class="page-subtitle">Create a task and assign Bank/NBFC logins to an employee</div>', unsafe_allow_html=True)

    emps = employees()
    emp_map = {e["full_name"]: e["id"] for e in emps}

    with st.form("raise_ticket_form"):
        c1, c2 = st.columns(2)
        with c1:
            customer = st.text_input("Customer / Company Name *")
            loan_type = st.selectbox("Loan Type", ["USL", "LAP", "HL", "Used Car", "Other"])
            amount = st.number_input("Required Amount", min_value=0.0, step=50000.0)
            surrogate = st.selectbox("Surrogate", ["Banking", "GST", "Financial", "Other"])
        with c2:
            assigned_name = st.selectbox("Assign To *", list(emp_map.keys()))
            priority = st.selectbox("Priority", ["High", "Medium", "Normal"])
            due = st.date_input("Due Date")
            remarks = st.text_area("Manager Remarks")

        lender_text = st.text_area(
            "Bank / NBFC Names *",
            placeholder="Enter one lender per line\nExample:\nHDFC Bank\nTata Capital\nPiramal Finance"
        )

        submitted = st.form_submit_button("Create Ticket", type="primary", use_container_width=True)

    if submitted:
        lenders = [x.strip() for x in lender_text.splitlines() if x.strip()]
        if not customer.strip():
            st.error("Customer / Company Name is required.")
        elif not lenders:
            st.error("Add at least one Bank / NBFC.")
        else:
            conn = get_conn()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO tickets(
                    customer_name,loan_type,required_amount,surrogate,assigned_to,
                    priority,due_date,manager_remarks,overall_status,created_by,
                    created_at,updated_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                customer.strip(), loan_type, amount, surrogate, emp_map[assigned_name],
                priority, due.isoformat(), remarks.strip(), "Open", user["id"],
                now, now
            ))
            ticket_id = cur.lastrowid
            ticket_no = f"GFS-{ticket_id:05d}"
            cur.execute("UPDATE tickets SET ticket_no=? WHERE id=?", (ticket_no, ticket_id))

            for lender in lenders:
                cur.execute("""
                    INSERT INTO ticket_lenders(ticket_id,lender_name,status,updated_at)
                    VALUES (?,?,?,?)
                """, (ticket_id, lender, "Pending", now))

            cur.execute("""
                INSERT INTO activity_log(ticket_id,user_id,action,created_at)
                VALUES (?,?,?,?)
            """, (
                ticket_id, user["id"],
                f"Ticket created and assigned to {assigned_name}",
                now
            ))
            conn.commit()
            conn.close()

            st.success(f"Ticket {ticket_no} created successfully and assigned to {assigned_name}.")

# ---------- ALL TICKETS ----------
elif user["role"] == "Manager" and menu == "All Tickets":
    st.title("All Tickets")
    st.markdown('<div class="page-subtitle">Search and review all office tickets in one place</div>', unsafe_allow_html=True)
    df = ticket_df()

    if df.empty:
        st.info("No tickets available.")
    else:
        c1,c2,c3 = st.columns(3)
        with c1:
            status_filter = st.selectbox("Status", ["All","Open","In Progress","Completed"])
        with c2:
            priority_filter = st.selectbox("Priority", ["All","High","Medium","Normal"])
        with c3:
            search = st.text_input("Search Customer / Ticket No.")

        f = df.copy()
        if status_filter != "All":
            f = f[f["overall_status"] == status_filter]
        if priority_filter != "All":
            f = f[f["priority"] == priority_filter]
        if search.strip():
            q = search.lower().strip()
            f = f[
                f["customer_name"].str.lower().str.contains(q, na=False) |
                f["ticket_no"].str.lower().str.contains(q, na=False)
            ]

        for _, row in f.iterrows():
            render_ticket_summary(row.to_dict())
            with st.expander(f"View details — {row['ticket_no']}"):
                st.write("**Manager Remarks:**", row["manager_remarks"] or "-")
                lender_rows = lenders_for(int(row["id"]))
                st.dataframe(
                    pd.DataFrame(lender_rows)[["lender_name","status","login_id","employee_remark","updated_at"]],
                    use_container_width=True,
                    hide_index=True
                )

# ---------- REPORTS ----------
elif user["role"] == "Manager" and menu == "Reports":
    st.title("Reports")
    st.markdown('<div class="page-subtitle">Simple downloadable ticket summary</div>', unsafe_allow_html=True)
    df = ticket_df()
    if df.empty:
        st.info("No data available.")
    else:
        report = df[[
            "ticket_no","customer_name","loan_type","required_amount","surrogate",
            "assigned_name","priority","due_date","overall_status","created_at","updated_at"
        ]].copy()
        st.dataframe(report, use_container_width=True, hide_index=True)
        csv = report.to_csv(index=False).encode("utf-8")
        st.download_button(
            "Download Ticket Report CSV",
            csv,
            "ticket_report.csv",
            "text/csv",
            use_container_width=True
        )

# ---------- EMPLOYEE DASHBOARD ----------
elif user["role"] == "Employee" and menu == "My Dashboard":
    st.title(f"{user['full_name']} — My Dashboard")
    df = ticket_df("t.assigned_to=?", (user["id"],))

    total = len(df)
    open_count = int((df["overall_status"] == "Open").sum()) if not df.empty else 0
    in_prog = int((df["overall_status"] == "In Progress").sum()) if not df.empty else 0
    completed = int((df["overall_status"] == "Completed").sum()) if not df.empty else 0

    st.markdown('<div class="page-subtitle">Your assigned tasks and current progress</div>', unsafe_allow_html=True)
    render_kpis([
        ("Assigned", total),
        ("Open", open_count),
        ("In Progress", in_prog),
        ("Completed", completed),
    ])

    st.subheader("My Recent Tickets")
    if df.empty:
        st.info("No tickets assigned to you.")
    else:
        for _, row in df.head(8).iterrows():
            render_ticket_summary(row.to_dict())

# ---------- EMPLOYEE TICKETS ----------
elif user["role"] == "Employee" and menu == "My Tickets":
    st.title("My Tickets")
    st.markdown('<div class="page-subtitle">Update lender-wise login status and remarks</div>', unsafe_allow_html=True)
    df = ticket_df("t.assigned_to=?", (user["id"],))

    if df.empty:
        st.info("No tickets assigned to you.")
    else:
        status_pick = st.selectbox("Filter", ["All","Open","In Progress","Completed"])
        if status_pick != "All":
            df = df[df["overall_status"] == status_pick]

        for _, row in df.iterrows():
            render_ticket_summary(row.to_dict())
            with st.expander(f"Update {row['ticket_no']} — {row['customer_name']}"):
                st.write("**Manager Remarks:**", row["manager_remarks"] or "-")
                lender_rows = lenders_for(int(row["id"]))

                for lender in lender_rows:
                    st.markdown(f"### {lender['lender_name']}")
                    c1,c2 = st.columns(2)
                    with c1:
                        statuses = ["Pending","Login Done","Rejected","Documents Required","Re-login / Rework"]
                        current_index = statuses.index(lender["status"]) if lender["status"] in statuses else 0
                        new_status = st.selectbox(
                            "Status",
                            statuses,
                            index=current_index,
                            key=f"status_{lender['id']}"
                        )
                        login_id = st.text_input(
                            "Application / Login ID",
                            value=lender["login_id"] or "",
                            key=f"login_{lender['id']}"
                        )
                    with c2:
                        emp_remark = st.text_area(
                            "Employee Remark",
                            value=lender["employee_remark"] or "",
                            key=f"remark_{lender['id']}"
                        )

                    if st.button(
                        f"Save {lender['lender_name']}",
                        key=f"save_{lender['id']}",
                        type="primary"
                    ):
                        conn = get_conn()
                        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        conn.execute("""
                            UPDATE ticket_lenders
                            SET status=?, login_id=?, employee_remark=?, updated_at=?
                            WHERE id=?
                        """, (new_status, login_id.strip(), emp_remark.strip(), now, lender["id"]))
                        conn.commit()
                        conn.close()

                        add_activity(
                            int(row["id"]),
                            user["id"],
                            f"{lender['lender_name']} updated to {new_status}"
                        )
                        recalc_ticket(int(row["id"]))
                        st.success("Updated successfully.")
                        st.rerun()

                    st.divider()

                # Progress
                updated_lenders = lenders_for(int(row["id"]))
                total_lenders = len(updated_lenders)
                done = sum(1 for x in updated_lenders if x["status"] == "Login Done")
                if total_lenders:
                    st.progress(done / total_lenders)
                    st.caption(f"{done} of {total_lenders} lender logins completed")

                st.subheader("Activity History")
                conn = get_conn()
                logs = conn.execute("""
                    SELECT a.*, u.full_name
                    FROM activity_log a
                    LEFT JOIN users u ON a.user_id=u.id
                    WHERE a.ticket_id=?
                    ORDER BY a.id DESC
                """, (int(row["id"]),)).fetchall()
                conn.close()

                if logs:
                    hist = pd.DataFrame([dict(x) for x in logs])
                    st.dataframe(
                        hist[["created_at","full_name","action"]],
                        use_container_width=True,
                        hide_index=True
                    )
