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
# 📦 DATABASE SCHEMA (customer_sales)
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
    st.write("Enter your password to access the AI SQL Query Assistant.")

    password = st.text_input("Password", type="password", key="login_password")

    col1, _, _ = st.columns([1, 1, 3])
    with col1:
        login_btn = st.button("🔓 Login", type="primary", use_container_width=True)

    if login_btn:
        if password:
            if bcrypt.checkpw(password.encode("utf-8"), HASHED_PASSWORD):
                st.session_state.logged_in = True
                st.success("✅ Authentication successful! Redirecting...")
                st.rerun()
            else:
                st.error("❌ Incorrect password")
        else:
            st.warning("⚠️ Please enter a password")

    st.markdown("---")
    st.info(
        """
        **Security Notice:**
        - Passwords stored using bcrypt hashing
        - Session remains active until closed or logout
        """
    )


def require_login():
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_screen()
        st.stop()


# -------------------------------------------------------------------
# 🛢️ DATABASE ENGINE (SQLAlchemy)
# -------------------------------------------------------------------
@st.cache_resource
def get_engine():
    POSTGRES_USERNAME = st.secrets["POSTGRES_USERNAME"]
    POSTGRES_PASSWORD = st.secrets["POSTGRES_PASSWORD"]
    POSTGRES_SERVER = st.secrets["POSTGRES_SERVER"]
    POSTGRES_DATABASE = st.secrets["POSTGRES_DATABASE"]

    url = (
        f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_SERVER}/{POSTGRES_DATABASE}"
    )

    engine = create_engine(url, pool_pre_ping=True, pool_recycle=3600)
    return engine


def run_query(sql):
    engine = get_engine()
    try:
        df = pd.read_sql_query(text(sql), engine)
        return df
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
    return re.sub(
        r"^```sql\s*|\s*```$", "", response_text, flags=re.MULTILINE | re.IGNORECASE
    ).strip()


def generate_sql_with_gpt(user_question):
    client = get_openai_client()

    prompt = f"""
You are a PostgreSQL expert. Given the following customer-sales schema and a user question, generate a valid PostgreSQL query.

{DATABASE_SCHEMA}

User Question: {user_question}

Rules:
1. Output ONLY SQL (no markdown).
2. Use exact quoted identifiers (e.g., "Customer", "OrderDetail").
3. Use correct JOIN paths:
   - "OrderDetail" → "Customer" → "Country" → "Region"
   - "OrderDetail" → "Product" → "ProductCategory"
4. For revenue: "QuantityOrdered" * "ProductUnitPrice"
5. Add LIMIT 100 for large results.
6. Use clear aliases.

Generate the SQL query now:
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
# 🎨 STREAMLIT UI
# -------------------------------------------------------------------
def main():
    require_login()

    st.title("🤖 AI SQL Query Assistant — Customer Sales Database")
    st.write("Ask natural language questions and get SQL queries!")

    st.markdown("---")
    st.sidebar.title("💡 Examples")
    st.sidebar.write(
        """
• How many customers are in each country?  
• What is the total revenue by region?  
• What products generated the most sales?  
• Show the top 10 customers by total revenue.  
• Daily order counts this year.
"""
    )

    if st.sidebar.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()

    if "generated_sql" not in st.session_state:
        st.session_state.generated_sql = None

    # Ask question
    user_question = st.text_area(
        "What would you like to know?", height=100, placeholder="Example: Total revenue by product category"
    )

    if st.button("Generate SQL", type="primary"):
        with st.spinner("Generating SQL..."):
            st.session_state.generated_sql = generate_sql_with_gpt(user_question)

    # Show SQL
    if st.session_state.generated_sql:
        st.subheader("Generated SQL Query")
        edited_sql = st.text_area(
            "Edit if needed:",
            value=st.session_state.generated_sql,
            height=200,
        )

        if st.button("Run Query", type="primary"):
            with st.spinner("Running query..."):
                df = run_query(edited_sql)
                if df is not None:
                    st.success(f"Returned {len(df)} rows")
                    st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()
