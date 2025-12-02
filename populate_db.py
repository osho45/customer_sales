# populate_db.py

import os
import psycopg2
from psycopg2 import sql
from psycopg2 import extras
from psycopg2.extras import execute_values

from utils import get_db_url


SCHEMA_SQL="""
DROP TABLE IF EXISTS "OrderDetail" CASCADE;
DROP TABLE IF EXISTS "Product" CASCADE;
DROP TABLE IF EXISTS "ProductCategory" CASCADE;
DROP TABLE IF EXISTS "Customer" CASCADE;
DROP TABLE IF EXISTS "Country" CASCADE;
DROP TABLE IF EXISTS "Region" CASCADE;

CREATE TABLE "Region" (
    "RegionID"   SERIAL PRIMARY KEY,
    "Region"     TEXT NOT NULL
);

CREATE TABLE "Country" (
    "CountryID"  SERIAL PRIMARY KEY,
    "Country"    TEXT NOT NULL,
    "RegionID"   INTEGER NOT NULL,
    FOREIGN KEY ("RegionID") REFERENCES "Region"("RegionID")
);

CREATE TABLE "Customer" (
    "CustomerID" INTEGER PRIMARY KEY GENERATED ALWAYS AS IDENTITY,
    "FirstName"  TEXT NOT NULL,
    "LastName"   TEXT NOT NULL,
    "Address"    TEXT NOT NULL,
    "City"       TEXT NOT NULL,
    "CountryID"  INTEGER NOT NULL,
    FOREIGN KEY ("CountryID") REFERENCES "Country"("CountryID")
);

CREATE TABLE "ProductCategory" (
    "ProductCategoryID"     SERIAL PRIMARY KEY,
    "ProductCategory"       TEXT NOT NULL,
    "ProductCategoryDescription" TEXT NOT NULL
);

CREATE TABLE "Product" (
    "ProductID"        SERIAL PRIMARY KEY,
    "ProductName"      TEXT NOT NULL,
    "ProductUnitPrice" REAL NOT NULL,
    "ProductCategoryID" INTEGER NOT NULL,
    FOREIGN KEY ("ProductCategoryID") REFERENCES "ProductCategory"("ProductCategoryID")
);
CREATE TABLE "OrderDetail" (
    "OrderID"         SERIAL PRIMARY KEY,
    "CustomerID"      INTEGER NOT NULL,
    "ProductID"       INTEGER NOT NULL,
    "OrderDate"       DATE NOT NULL,
    "QuantityOrdered" INTEGER NOT NULL,
    FOREIGN KEY ("CustomerID") REFERENCES "Customer"("CustomerID"),
    FOREIGN KEY ("ProductID") REFERENCES "Product"("ProductID")
);
"""


def split_name(full_name: str):
    full_name=full_name.strip()
    parts=full_name.split(maxsplit=1)
    if len(parts)==2:
        first, last=parts
    else:
        first, last=parts[0], ""
    return first, last


def parse_date_yyyymmdd(s: str) -> str:
    s=s.strip()
    if len(s)==8 and s.isdigit():
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    return s


def read_raw_data(data_filename: str):
    regions=set()
    countries=set()  
    customers=set()  
    product_categories=set() 
    products=set()  
    order_lines=[] 

    with open(data_filename, "r", encoding="utf-8") as f:
        header=f.readline()
        for line in f:
            line=line.strip()
            if not line:
                continue

            cols=line.split("\t")
            if len(cols) < 11:
                continue

            name_raw=cols[0].strip()
            address=cols[1].strip()
            city=cols[2].strip()
            country_name=cols[3].strip()
            region_name=cols[4].strip()

            product_names_field=cols[5].strip()
            product_category_field=cols[6].strip()
            product_category_desc_field=cols[7].strip()
            price_field=cols[8].strip()
            qty_field=cols[9].strip()
            date_field=cols[10].strip()

            if region_name:
                regions.add(region_name)
            if country_name and region_name:
                countries.add((country_name, region_name))

            if name_raw and address and city and country_name:
                first_name, last_name=split_name(name_raw)
                customers.add((first_name, last_name, address, city, country_name))

            if not product_names_field:
                continue

            product_names=[p.strip() for p in product_names_field.split(";") if p.strip()]
            product_categories_raw=[c.strip() for c in product_category_field.split(";") if c.strip()]
            product_cat_descs=[d.strip() for d in product_category_desc_field.split(";") if d.strip()]
            prices_raw=[p.strip() for p in price_field.split(";") if p.strip()]
            qtys_raw=[q.strip() for q in qty_field.split(";") if q.strip()]
            dates_raw=[d.strip() for d in date_field.split(";") if d.strip()]

            for cat_name, cat_desc in zip(product_categories_raw, product_cat_descs):
                product_categories.add((cat_name, cat_desc))

            for pname, price_str, cat_name in zip(product_names, prices_raw, product_categories_raw):
                try:
                    price_val=float(price_str)
                except ValueError:
                    continue
                products.add((pname, price_val, cat_name))

            first_name, last_name=split_name(name_raw)
            if last_name:
                full_name_key=f"{first_name} {last_name}"
            else:
                full_name_key=first_name

            for pname, qty_str, d_raw in zip(product_names, qtys_raw, dates_raw):
                if not pname or not qty_str or not d_raw:
                    continue
                try:
                    qty_val=int(qty_str)
                except ValueError:
                    continue
                order_date=parse_date_yyyymmdd(d_raw)
                order_lines.append((full_name_key, pname, order_date, qty_val))

    return {
        "regions": regions,
        "countries": countries,
        "customers": customers,
        "product_categories": product_categories,
        "products": products,
        "order_lines": order_lines,
    }


def create_schema(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)


def insert_dimensions(conn, data):
    regions=sorted(data["regions"])
    countries=sorted(data["countries"], key=lambda x: (x[0], x[1]))
    customers=sorted(data["customers"], key=lambda x: (x[0], x[1]))
    product_categories=sorted(data["product_categories"], key=lambda x: x[0])
    products=sorted(data["products"], key=lambda x: x[0])

    region_id_map={}
    country_id_map={}
    customer_id_map={}
    product_cat_id_map={}
    product_id_map={}

    with conn:
        with conn.cursor() as cur:
            if regions:
                cur.executemany(
                    'INSERT INTO "Region" ("Region") VALUES (%s)',
                    [(r,) for r in regions],
                )

    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "RegionID", "Region" FROM "Region"')
            for rid, rname in cur.fetchall():
                region_id_map[rname]=rid

    with conn:
        with conn.cursor() as cur:
            rows=[]
            for country_name, region_name in countries:
                region_id=region_id_map.get(region_name)
                if region_id is not None:
                    rows.append((country_name, region_id))
            if rows:
                cur.executemany(
                    'INSERT INTO "Country" ("Country", "RegionID") VALUES (%s, %s)',
                    rows,
                )

    with conn:
        with conn.cursor() as cur:
            cur.execute('SELECT "CountryID", "Country" FROM "Country"')
            for cid, cname in cur.fetchall():
                country_id_map[cname]=cid

    with conn:
        with conn.cursor() as cur:
            rows=[]
            for cat_name, cat_desc in product_categories:
                rows.append((cat_name, cat_desc))
            if rows:
                cur.executemany(
                    'INSERT INTO "ProductCategory" ("ProductCategory", "ProductCategoryDescription") '
                    'VALUES (%s, %s)',
                    rows,
                )

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ProductCategoryID", "ProductCategory" FROM "ProductCategory"'
            )
            for pcid, pcname in cur.fetchall():
                product_cat_id_map[pcname]=pcid

    with conn:
        with conn.cursor() as cur:
            rows=[]
            for pname, price_val, cat_name in products:
                cat_id=product_cat_id_map.get(cat_name)
                if cat_id is not None:
                    rows.append((pname, price_val, cat_id))
            if rows:
                cur.executemany(
                    'INSERT INTO "Product" ("ProductName", "ProductUnitPrice", "ProductCategoryID") '
                    'VALUES (%s, %s, %s)',
                    rows,
                )

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "ProductID", "ProductName" FROM "Product"'
            )
            for pid, pname in cur.fetchall():
                product_id_map[pname]=pid

    with conn:
        with conn.cursor() as cur:
            rows=[]
            for first, last, addr, city, country_name in customers:
                country_id=country_id_map.get(country_name)
                if country_id is not None:
                    rows.append((first, last, addr, city, country_id))
            if rows:
                cur.executemany(
                    'INSERT INTO "Customer" ("FirstName", "LastName", "Address", "City", "CountryID") '
                    'VALUES (%s, %s, %s, %s, %s)',
                    rows,
                )

    with conn:
        with conn.cursor() as cur:
            cur.execute(
                'SELECT "CustomerID", "FirstName", "LastName" FROM "Customer"'
            )
            for cid, first, last in cur.fetchall():
                full=f"{first} {last}".strip()
                customer_id_map[full]=cid

    return region_id_map, country_id_map, customer_id_map, product_cat_id_map, product_id_map



def insert_orders(conn, data, customer_id_map, product_id_map):

    order_rows=[]
    for full_name_key, product_name, order_date_str, qty in data["order_lines"]:
        cust_id=customer_id_map.get(full_name_key)
        prod_id=product_id_map.get(product_name)
        if cust_id is None or prod_id is None:
            continue
        order_rows.append((cust_id, prod_id, order_date_str, qty))

    with conn:
        with conn.cursor() as cur:
            sql='''
                INSERT INTO "OrderDetail"
                ("CustomerID", "ProductID", "OrderDate", "QuantityOrdered")
                VALUES %s
            '''
            execute_values(cur, sql, order_rows)



def main():
    base_dir=os.path.dirname(os.path.abspath(__file__))
    data_file=os.path.join(base_dir, "data.csv")

    db_url=get_db_url()
    conn=psycopg2.connect(db_url)

    try:
        print("Creating schema...")
        create_schema(conn)

        print("Reading raw data from", data_file)
        data=read_raw_data(data_file)
        print("  Regions:", len(data["regions"]))
        print("  Countries:", len(data["countries"]))
        print("  Customers:", len(data["customers"]))
        print("  ProductCategories:", len(data["product_categories"]))
        print("  Products:", len(data["products"]))
        print("  Order lines:", len(data["order_lines"]))

        print("Inserting dimensions...")
        _, _, customer_id_map, _, product_id_map=insert_dimensions(conn, data)

        print("Inserting order details...")
        insert_orders(conn, data, customer_id_map, product_id_map)

        print("populate_db completed successfully.")
    finally:
        conn.close()


if __name__=="__main__":
    main()
