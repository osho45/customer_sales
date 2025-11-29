import re
import streamlit as st
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI
import os
import bcrypt
from sqlalchemy import create_engine, text

load_dotenv()

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
HASHED_PASSWORD = st.secrets["HASHED_PASSWORD"].encode("utf-8")

# -------------------------------------------------------------------
# 📦 DATABASE SCHEMA
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
# 🔐 LOGIN
# -------------------------------------------------------------------
def login_screen():
    st.title("🔐 Secure Login")
    st.markdown("---")
    st.write("Enter your password to access the AI SQL Navigator.")

    password = st.text_input("Password", type="password", key="login_password")

    if st.button("Login"):
        if password and bcrypt.checkpw(password.encode("utf-8"), HASHED_PASSWORD):
            st.session_state.logged_in = True
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Incorrect password")

def require_login():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_screen()
        st.stop()

# -------------------------------------------------------------------
# 🛢️ DATABASE ENGINE
# -------------------------------------------------------------------
@st.cache_resource
def get_engine():
    POSTGRES_USERNAME = st.secrets["POSTGRES_USERNAME"]
    POSTGRES_PASSWORD = st.secrets["POSTGRES_PASSWORD"]
    POSTGRES_SERVER = st.secrets["POSTGRES_SERVER"]
    POSTGRES_DATABASE = st.secrets["POSTGRES_DATABASE"]

    url = f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@{POSTGRES_SERVER}/{POSTGRES_DATABASE}"
    return create_engine(url, pool_pre_ping=True, pool_recycle=3600)

def run_query(sql):
    engine = get_engine()
    try:
        return pd.read_sql_query(text(sql), engine)
    except Exception as e:
        st.error(f"Error executing query: {e}")
        return None

# -------------------------------------------------------------------
# 🤖 OPENAI CLIENT
# -------------------------------------------------------------------
@st.cache_resource
def get_openai_client():
    return OpenAI(api_key=OPENAI_API_KEY)

def extract_sql_from_response(response_text):
    return re.sub(r"^```sql\s*|\s*```$", "", response_text, flags=re.MULTILINE | re.IGNORECASE).strip()

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
# 🧹 CUSTOM CSS (Sidebar width + no scroll + green buttons)
# -------------------------------------------------------------------
st.markdown("""
<style>

[data-testid="stSidebar"] {
    min-width: 240px !important;
    max-width: 240px !important;
    width: 240px !important;
}

/* Remove scroll inside sidebar */
[data-testid="stSidebar"] .css-1lcbmhc, 
[data-testid="stSidebar"] .css-1r6slb0 {
    overflow-y: hidden !important;
}

/* Green buttons */
button[kind="primary"] {
    background-color: #0FA958 !important;
    color: white !important;
}

/* Logout button wrapper */
.sidebar-footer {
    margin-top: 40px;
    padding-top: 20px;
}

</style>
""", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 🎨 SIDEBAR
# -------------------------------------------------------------------
with st.sidebar:
    st.subheader("💡 Examples")
    st.write("""
- How many customers are in each country?  
- What is the total revenue by region?  
- What products generated the most sales?  
- Show the top 10 customers by total revenue.  
- Daily order counts this year.
""")

    st.markdown('<div class="sidebar-footer">', unsafe_allow_html=True)
    if st.button("📕 Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

# -------------------------------------------------------------------
# 🎨 MAIN APP LAYOUT
# -------------------------------------------------------------------
def main():
    require_login()

    st.title("🤖 AI SQL Navigator — Sales & Customer Insights")
    st.write("✨ Natural language in, SQL out.")
    st.markdown("---")

    if "query_history" not in st.session_state:
        st.session_state.query_history = []

    user_question = st.text_area("What’s on your mind?", height=90)

    if st.button("Generate SQL", type="primary"):
        sql = generate_sql_with_gpt(user_question)
        if sql:
            st.session_state.generated_sql = sql
            st.session_state.query_history.append(user_question)

    if "generated_sql" in st.session_state:
        st.subheader("Generated SQL Query")
        edited_sql = st.text_area("Edit if needed:", value=st.session_state.generated_sql, height=180)

        if st.button("Run Query", type="primary"):
            df = run_query(edited_sql)
            if df is not None:
                st.success(f"Returned {len(df)} rows")
                st.dataframe(df, use_container_width=True)

    st.markdown("---")
    st.subheader("📜 Query History")

    for q in reversed(st.session_state.query_history):
        st.expander(q).write("")

# Run app
if __name__ == "__main__":
    main()
