import re
import streamlit as st
import pandas as pd
import psycopg2
from dotenv import load_dotenv
from openai import OpenAI
import os
import bcrypt

load_dotenv()  # reads variables from a .env file and sets them in os.environ

OPENAI_API_KEY = st.secrets["OPENAI_API_KEY"]
HASHED_PASSWORD = st.secrets["HASHED_PASSWORD"].encode("utf-8")

# -------------------------------------------------------------------
# 📦 Database schema description (based on populate_db.py)
# -------------------------------------------------------------------
DATABASE_SCHEMA = """
Database Schema (Customer Orders):

TABLE: "Region"
- "RegionID"   SERIAL PRIMARY KEY
- "Region"     TEXT NOT NULL

TABLE: "Country"
- "CountryID"  SERIAL PRIMARY KEY
- "Country"    TEXT NOT NULL
- "RegionID"   INTEGER NOT NULL REFERENCES "Region"("RegionID")

TABLE: "Customer"
- "CustomerID" INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY
- "FirstName"  TEXT NOT NULL
- "LastName"   TEXT NOT NULL
- "Address"    TEXT NOT NULL
- "City"       TEXT NOT NULL
- "CountryID"  INTEGER NOT NULL REFERENCES "Country"("CountryID")

TABLE: "ProductCategory"
- "ProductCategoryID"          SERIAL PRIMARY KEY
- "ProductCategory"            TEXT NOT NULL
- "ProductCategoryDescription" TEXT NOT NULL

TABLE: "Product"
- "ProductID"         SERIAL PRIMARY KEY
- "ProductName"       TEXT NOT NULL
- "ProductUnitPrice"  REAL NOT NULL
- "ProductCategoryID" INTEGER NOT NULL REFERENCES "ProductCategory"("ProductCategoryID")

TABLE: "OrderDetail"
- "OrderID"         SERIAL PRIMARY KEY
- "CustomerID"      INTEGER NOT NULL REFERENCES "Customer"("CustomerID")
- "ProductID"       INTEGER NOT NULL REFERENCES "Product"("ProductID")
- "OrderDate"       DATE NOT NULL
- "QuantityOrdered" INTEGER NOT NULL

Relationships / Notes:
- Each customer belongs to a country; each country belongs to a region.
- Each product belongs to a product category.
- Each order line links a customer to a product on a given date with a quantity.
- Revenue for a line = "QuantityOrdered" * "ProductUnitPrice".
- To get country or region for an order, JOIN "OrderDetail" -> "Customer" -> "Country" -> "Region".
- IMPORTANT: Table and column names are mixed-case and created with double quotes.
  When writing SQL, always use these exact names with double quotes, e.g. "OrderDetail", "CustomerID".
"""


# -------------------------------------------------------------------
# 🔐 Login
# -------------------------------------------------------------------
def login_screen():
    """Display login screen and authenticate user."""
    st.title("🔐 Secure Login")
    st.markdown("---")
    st.write("Enter your password to access the AI SQL Query Assistant.")
    
    password = st.text_input("Password", type="password", key="login_password")
    
    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        login_btn = st.button("🔓 Login", type="primary", use_container_width=True)
    
    if login_btn:
        if password:
            try:
                if bcrypt.checkpw(password.encode("utf-8"), HASHED_PASSWORD):
                    st.session_state.logged_in = True
                    st.success("✅ Authentication successful! Redirecting...")
                    st.rerun()
                else:
                    st.error("❌ Incorrect password")
            except Exception as e:
                st.error(f"❌ Authentication error: {e}")
        else:
            st.warning("⚠️ Please enter a password")
    
    st.markdown("---")
    st.info(
        """
        **Security Notice:**
        - Passwords are protected using bcrypt hashing
        - Your session is secure and isolated
        - You will remain logged in until you close the browser or click logout
        """
    )


def require_login():
    """Enforce login before showing main app."""
    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        login_screen()
        st.stop()


# -------------------------------------------------------------------
# 🗄️ Database connection helpers
# -------------------------------------------------------------------
@st.cache_resource
def get_db_url():
    POSTGRES_USERNAME = st.secrets["POSTGRES_USERNAME"]
    POSTGRES_PASSWORD = st.secrets["POSTGRES_PASSWORD"]
    POSTGRES_SERVER = st.secrets["POSTGRES_SERVER"]
    POSTGRES_DATABASE = st.secrets["POSTGRES_DATABASE"]

    DATABASE_URL = (
        f"postgresql://{POSTGRES_USERNAME}:{POSTGRES_PASSWORD}@"
        f"{POSTGRES_SERVER}/{POSTGRES_DATABASE}"
    )
    return DATABASE_URL


DATABASE_URL = get_db_url()


@st.cache_resource
def get_db_connection():
    """Create and cache database connection."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        st.error(f"Failed to connect to database: {e}")
        return None


def run_query(sql: str):
    """Execute SQL query and return results as DataFrame."""
    conn = get_db_connection()
    if conn is None:
        return None
    
    try:
        df = pd.read_sql_query(sql, conn)
        return df
    except Exception as e:
        st.error(f"Error executing query: {e}")
        return None


# -------------------------------------------------------------------
# 🤖 OpenAI helpers
# -------------------------------------------------------------------
@st.cache_resource
def get_openai_client():
    """Create and cache OpenAI client."""
    return OpenAI(api_key=OPENAI_API_KEY)


def extract_sql_from_response(response_text: str) -> str:
    """Strip ```sql ... ``` fences if present."""
    clean_sql = re.sub(
        r"^```sql\s*|\s*```$",
        "",
        response_text,
        flags=re.IGNORECASE | re.MULTILINE,
    ).strip()
    return clean_sql


def generate_sql_with_gpt(user_question: str):
    client = get_openai_client()
    prompt = f"""You are a PostgreSQL expert. Given the following customer-orders database schema and a user's question, generate a valid PostgreSQL query.

{DATABASE_SCHEMA}

User Question: {user_question}

Requirements:
1. Generate ONLY the SQL query that I can directly use. No explanation, no markdown.
2. Always use the exact mixed-case table and column names with double quotes, e.g. "OrderDetail", "CustomerID", "ProductUnitPrice".
3. Use proper JOINs to navigate relationships:
   - "OrderDetail" -> "Customer" -> "Country" -> "Region"
   - "OrderDetail" -> "Product" -> "ProductCategory"
4. Use appropriate aggregations (COUNT, SUM, AVG, etc.) when needed.
5. For revenue-related questions, compute revenue as "QuantityOrdered" * "ProductUnitPrice".
6. Add LIMIT clauses (e.g. LIMIT 100) for queries that might return many rows.
7. Make sure the query is syntactically correct for PostgreSQL.
8. Add helpful column aliases using AS.

Generate the SQL query:"""

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a PostgreSQL expert who generates accurate SQL "
                        "queries for a customer orders database based on natural language questions."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=1000,
        )

        sql_query = extract_sql_from_response(
            response.choices[0].message.content
        )
        return sql_query

    except Exception as e:
        st.error(f"Error calling OpenAI API: {e}")
        return None


# -------------------------------------------------------------------
# 🎛️ Main Streamlit app
# -------------------------------------------------------------------
def main():
    require_login()
    st.title("🤖 AI-Powered SQL Query Assistant (Customer Orders)")
    st.markdown(
        "Ask questions in natural language, and I will generate SQL queries "
        "for your customer-orders database!"
    )
    st.markdown("---")

    # Sidebar examples
    st.sidebar.title("💡 Example Questions")
    st.sidebar.markdown(
        """
    Try asking questions like:

    **Customers / Geography:**
    - How many customers do we have in each country?
    - Show number of customers by region.
    - List all customers from the Asia region.

    **Products / Categories:**
    - What are the top 10 products by total quantity ordered?
    - Show total revenue by product category.
    - Which product category has the highest average order quantity?

    **Orders:**
    - What is the total revenue by country and region?
    - Show daily order counts for the last 30 days.
    - For each customer, show total orders and total revenue.
    """
    )

    st.sidebar.markdown("---")
    st.sidebar.info(
        """
        🧠 **How it works:**
        1. Enter your question in plain English
        2. AI generates a SQL query
        3. Review and optionally edit the query
        4. Click "Run Query" to execute
        """
    )

    st.sidebar.markdown("---")
    if st.sidebar.button("🚪 Logout"):
        st.session_state.logged_in = False
        st.rerun()

    # Init session state
    if "query_history" not in st.session_state:
        st.session_state.query_history = []
    if "generated_sql" not in st.session_state:
        st.session_state.generated_sql = None
    if "current_question" not in st.session_state:
        st.session_state.current_question = None

    # Main input
    user_question = st.text_area(
        "What would you like to know?",
        height=100,
        placeholder="Example: What is the total revenue by region?",
    )

    col1, col2, col3 = st.columns([1, 1, 4])
    with col1:
        generate_button = st.button("Generate SQL", type="primary", use_container_width=True)
    with col2:
        if st.button("Clear History", use_container_width=True):
            st.session_state.query_history = []
            st.session_state.generated_sql = None
            st.session_state.current_question = None

    if generate_button and user_question:
        user_question = user_question.strip()

        # Reset SQL if question changed
        if st.session_state.current_question != user_question:
            st.session_state.generated_sql = None
            st.session_state.current_question = None

        with st.spinner("🧠 AI is thinking and generating SQL..."):
            sql_query = generate_sql_with_gpt(user_question)
            if sql_query:
                st.session_state.generated_sql = sql_query
                st.session_state.current_question = user_question

    # Show generated SQL + results
    if st.session_state.generated_sql:
        st.markdown("---")
        st.subheader("Generated SQL Query")
        st.info(f"**Question:** {st.session_state.current_question}")

        edited_sql = st.text_area(
            "Review and edit the SQL query if needed:",
            value=st.session_state.generated_sql,
            height=200,
        )

        col1, col2 = st.columns([1, 5])
        with col1:
            run_button = st.button("Run Query", type="primary", use_container_width=True)

        if run_button:
            with st.spinner("Executing query..."):
                df = run_query(edited_sql)
                if df is not None:
                    st.session_state.query_history.append(
                        {
                            "question": st.session_state.current_question,
                            "sql": edited_sql,
                            "rows": len(df),
                        }
                    )

                    st.markdown("---")
                    st.subheader("📊 Query Results")
                    st.success(f"✅ Query returned {len(df)} rows")
                    st.dataframe(df, use_container_width=True)

    # Query history
    if st.session_state.query_history:
        st.markdown("---")
        st.subheader("📜 Query History")
        for idx, item in enumerate(reversed(st.session_state.query_history[-5:])):
            label = f"Query {len(st.session_state.query_history) - idx}: {item['question'][:60]}..."
            with st.expander(label):
                st.markdown(f"**Question:** {item['question']}")
                st.code(item["sql"], language="sql")
                st.caption(f"Returned {item['rows']} rows")
                if st.button("Re-run this query", key=f"rerun_{idx}"):
                    df = run_query(item["sql"])
                    if df is not None:
                        st.dataframe(df, use_container_width=True)


if __name__ == "__main__":
    main()
