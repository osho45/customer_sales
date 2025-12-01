import re
import bcrypt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from sqlalchemy import create_engine, text


load_dotenv()
st.set_page_config(page_title="SQL Copilot", page_icon="🛰️", layout="wide")

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
HASHED_PASSWORD = st.secrets["HASHED_PASSWORD"].encode("utf-8")

# -------------------------------------------------------------------
# DATABASE SCHEMA (for the prompt)
# -------------------------------------------------------------------
DATABASE_SCHEMA = """
Database Schema (Customer Sales):

TABLE: "Region" (
    "RegionID"   SERIAL PRIMARY KEY,
    "Region"     TEXT NOT NULL
)

TABLE: "Country" (
    "CountryID"  SERIAL PRIMARY KEY,
    "Country"    TEXT NOT NULL,
    "RegionID"   INTEGER NOT NULL REFERENCES "Region"("RegionID")
)

TABLE: "Customer" (
    "CustomerID" INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    "FirstName"  TEXT NOT NULL,
    "LastName"   TEXT NOT NULL,
    "Address"    TEXT NOT NULL,
    "City"       TEXT NOT NULL,
    "CountryID"  INTEGER NOT NULL REFERENCES "Country"("CountryID")
)

TABLE: "ProductCategory" (
    "ProductCategoryID" SERIAL PRIMARY KEY,
    "ProductCategory" TEXT NOT NULL,
    "ProductCategoryDescription" TEXT NOT NULL
)

TABLE: "Product" (
    "ProductID" SERIAL PRIMARY KEY,
    "ProductName" TEXT NOT NULL,
    "ProductUnitPrice" REAL NOT NULL,
    "ProductCategoryID" INTEGER NOT NULL REFERENCES "ProductCategory"("ProductCategoryID")
)

TABLE: "OrderDetail" (
    "OrderID" SERIAL PRIMARY KEY,
    "CustomerID" INTEGER NOT NULL REFERENCES "Customer"("CustomerID"),
    "ProductID" INTEGER NOT NULL REFERENCES "Product"("ProductID"),
    "OrderDate" DATE NOT NULL,
    "QuantityOrdered" INTEGER NOT NULL
)
"""

# -------------------------------------------------------------------
# LOGIN
# -------------------------------------------------------------------
def login_screen():
    st.markdown(
        """
        <div class="hero-icon">🔒</div>
        <h1 class="hero-title">Secure Workspace Login</h1>
        <p class="hero-sub">Enter your team password to access the AI SQL copilot.</p>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="divider"></div>', unsafe_allow_html=True)
    password = st.text_input("Password", type="password", key="login_password", placeholder="********")

    if st.button("Enter workspace", type="primary"):
        if password and bcrypt.checkpw(password.encode("utf-8"), HASHED_PASSWORD):
            st.session_state.logged_in = True
            st.success("Login successful")
            st.rerun()
        else:
            st.error("Incorrect password. Please try again.")


def require_login():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_screen()
        st.stop()


# -------------------------------------------------------------------
# DATABASE ENGINE
# -------------------------------------------------------------------
@st.cache_resource
def get_engine():
    username = st.secrets["POSTGRES_USERNAME"]
    password = st.secrets["POSTGRES_PASSWORD"]
    server = st.secrets["POSTGRES_SERVER"]
    database = st.secrets["POSTGRES_DATABASE"]
    url = f"postgresql://{username}:{password}@{server}/{database}"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)


def run_query(sql):
    engine = get_engine()
    try:
        return pd.read_sql_query(text(sql), engine)
    except Exception as e:
        st.error(f"Error executing query: {e}")
        return None


# -------------------------------------------------------------------
# OPENAI CLIENT
# -------------------------------------------------------------------
@st.cache_resource
def get_openai_client():
    return OpenAI(api_key=OPENAI_API_KEY)


def extract_sql_from_response(response_text):
    return re.sub(r"^```sql\\s*|\\s*```$", "", response_text, flags=re.MULTILINE | re.IGNORECASE).strip()


def generate_sql_with_gpt(user_question):
    client = get_openai_client()
    prompt = f"""
You are a PostgreSQL expert. Generate a valid SQL query.

{DATABASE_SCHEMA}

User Question: {user_question}

Rules:
1. Output ONLY SQL (no markdown).
2. Use exact quoted identifiers.
3. Use correct join paths.
4. Revenue = QuantityOrdered * ProductUnitPrice.
5. Add LIMIT 100 for large results.
"""
    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You generate SQL queries precisely."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
        )
        return extract_sql_from_response(response.choices[0].message.content)
    except Exception as e:
        st.error(f"OpenAI error: {e}")
        return None


# -------------------------------------------------------------------
# THEME / STYLES
# -------------------------------------------------------------------
GLOBAL_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500&display=swap');

:root {
    --bg-1: #050b17;
    --bg-2: #0c1629;
    --card: rgba(255, 255, 255, 0.04);
    --border: rgba(255, 255, 255, 0.08);
    --accent: #6dd3ff;
    --accent-2: #a855f7;
    --text: #e5e7eb;
    --muted: #94a3b8;
}

html, body, [data-testid="stAppViewContainer"] {
    background: radial-gradient(circle at 20% 20%, rgba(109,211,255,0.05), transparent 20%),
                radial-gradient(circle at 80% 0%, rgba(168,85,247,0.08), transparent 25%),
                linear-gradient(145deg, var(--bg-1), var(--bg-2));
    color: var(--text);
    font-family: 'Inter', system-ui, sans-serif;
}

.hero-title {
    font-family: 'Space Grotesk', 'Inter', system-ui, sans-serif;
    font-size: 42px;
    font-weight: 700;
    letter-spacing: -0.02em;
    margin-bottom: 6px;
}

.hero-sub {
    color: var(--muted);
    font-size: 16px;
    margin-top: 0;
}

.hero-icon {
    font-size: 32px;
    margin-bottom: 8px;
}

.eyebrow {
    font-size: 13px;
    color: var(--accent);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    font-weight: 600;
    margin-bottom: 4px;
}

.glass-card {
    background: var(--card);
    border: 1px solid var(--border);
    border-radius: 18px;
    padding: 18px 18px 14px 18px;
    box-shadow: 0 15px 45px rgba(0,0,0,0.25), 0 0 0 1px rgba(255,255,255,0.02);
}

.divider {
    border-bottom: 1px solid var(--border);
    margin: 16px 0;
}

.sidebar-card {
    background: var(--card);
    border-radius: 16px;
    padding: 14px;
    border: 1px solid var(--border);
}

.history-item {
    border: 1px solid var(--border);
    border-radius: 14px;
    padding: 12px 14px;
    margin-bottom: 10px;
    background: rgba(255,255,255,0.02);
}

.history-item strong {
    color: var(--text);
}

.muted {
    color: var(--muted);
    font-size: 13px;
}

.chat-shell {
    background: rgba(255,255,255,0.04);
    border: 1px solid var(--border);
    border-radius: 999px;
    padding: 8px 12px;
}

.chat-shell input {
    background: transparent !important;
    border: none !important;
    color: var(--text) !important;
}

.chat-icon {
    color: var(--muted);
    font-size: 18px;
    display: flex;
    align-items: center;
    justify-content: center;
}

.chat-icon.accent {
    background: #0fa958;
    color: #0b0f19;
    width: 34px;
    height: 34px;
    border-radius: 50%;
}

button[kind="primary"] {
    background: linear-gradient(135deg, #34d399, #10b981) !important;
    color: #0b0f19 !important;
    font-weight: 700 !important;
    border: none !important;
}

[data-testid="stSidebar"] {
    background: rgba(0,0,0,0.25);
}

/* Hide heading link icons */
h1 a, h2 a, h3 a, h4 a {
    display: none !important;
}
</style>
"""


# -------------------------------------------------------------------
# MAIN APP LAYOUT
# -------------------------------------------------------------------
def render_sidebar(examples):
    with st.sidebar:
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### Quick prompts")
        for ex in examples:
            st.markdown(f"- {ex}")
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown("<div style='height: 14px'></div>", unsafe_allow_html=True)

        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("#### Session")
        if st.button("Logout", use_container_width=True):
            st.session_state.logged_in = False
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)


def render_hero():
    left, right = st.columns([1.6, 1])
    with left:
        st.markdown("<p class='eyebrow'>AI SQL Copilot 🤖</p>", unsafe_allow_html=True)
        st.markdown(
            "<h1 class='hero-title'>Ask a business question - Get production-ready SQL</h1>",
            unsafe_allow_html=True,
        )
    with right:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.metric("Queries this session", len(st.session_state.get("query_history", [])))
        st.markdown("</div>", unsafe_allow_html=True)


def render_query_area(user_question):
    st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
    st.markdown("### Where should we begin?")
    st.caption("Ask anything; we'll turn it into SQL.")

    st.markdown("<div class='chat-shell'>", unsafe_allow_html=True)
    c1, c2, c3, c4 = st.columns([0.08, 0.82, 0.05, 0.05])
    with c1:
        st.markdown("<div class='chat-icon'>＋</div>", unsafe_allow_html=True)
    with c2:
        question = st.text_input(
            label="",
            value=user_question,
            placeholder="Ask about: Region, Country, Customer, Product, ProductCategory, OrderDetail",
            label_visibility="collapsed",
        )
    with c3:
        st.markdown("<div class='chat-icon'>🎙️</div>", unsafe_allow_html=True)
    with c4:
        st.markdown("<div class='chat-icon accent'>🎛️</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    col1, col2 = st.columns([1, 1])
    submit = col1.button("Generate SQL", type="primary")
    clear = col2.button("Clear prompt")
    st.markdown("</div>", unsafe_allow_html=True)
    return question, submit, clear


def render_sql_and_results():
    if "generated_sql" in st.session_state:
        st.markdown("<div class='glass-card'>", unsafe_allow_html=True)
        st.markdown("### 🧠 Generated SQL")
        edited_sql = st.text_area("Edit or tweak", value=st.session_state.generated_sql, height=180)
        run = st.button("Run query", type="primary")
        st.markdown("</div>", unsafe_allow_html=True)

        if run:
            df = run_query(edited_sql)
            if df is not None:
                st.session_state.generated_sql = edited_sql
                st.success(f"Returned {len(df)} rows")
                st.dataframe(df, use_container_width=True)


def render_history():
    st.markdown("<div class='divider'></div>", unsafe_allow_html=True)
    st.markdown("### 📜 Query history")
    history = st.session_state.get("query_history", [])
    if not history:
        st.caption("No prompts yet. Your recent questions will appear here.")
        return
    for idx in range(len(history) - 1, -1, -1):
        item = history[idx]
        with st.expander(f"Q: {item['question']}", expanded=False):
            st.caption("SQL generated and saved")
            btn_cols = st.columns([1, 1, 1, 5])
            result_area = st.empty()
            run_df = None

            with btn_cols[0]:
                if st.button("Load", key=f"load_hist_{idx}", use_container_width=True):
                    st.session_state.generated_sql = item["sql"]
                    st.session_state.current_question = item["question"]
                    st.success("Loaded into the editor.")
                    st.rerun()
            with btn_cols[1]:
                if st.button("Run again", key=f"run_hist_{idx}", use_container_width=True):
                    st.session_state.generated_sql = item["sql"]
                    st.session_state.current_question = item["question"]
                    run_df = run_query(item["sql"])
            with btn_cols[2]:
                if st.button("Delete", key=f"delete_hist_{idx}", use_container_width=True):
                    del st.session_state.query_history[idx]
                    st.success("Removed from history.")
                    st.rerun()

            if run_df is not None:
                result_area.success(f"Ran history query - {len(run_df)} rows")
                result_area.dataframe(run_df, use_container_width=True)


def main():
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

    if "query_history" not in st.session_state:
        st.session_state.query_history = []

    require_login()

    examples = [
        "Which regions order the most high-priced products?",
        "First purchase date of every customer",
        "Top 10 products by gross margin.",
        "Longest streak of days with orders",
        "Which country has the highest revenue per customer?",
    ]
    render_sidebar(examples)
    render_hero()

    current_question = st.session_state.get("current_question", "")
    question, submit, clear = render_query_area(current_question)

    if clear:
        st.session_state.pop("generated_sql", None)
        st.session_state.current_question = ""
        st.rerun()

    if submit and question.strip():
        sql = generate_sql_with_gpt(question.strip())
        if sql:
            st.session_state.generated_sql = sql
            st.session_state.query_history.append({"question": question.strip(), "sql": sql})
            st.session_state.current_question = question.strip()
            st.rerun()
    elif submit and not question.strip():
        st.warning("Please enter a question first.")

    render_sql_and_results()
    render_history()


if __name__ == "__main__":
    main()
