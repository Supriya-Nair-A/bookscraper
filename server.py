import csv
import io
import math
import sqlite3
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from fastapi import FastAPI, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse

app = FastAPI(title="Books to Scrape ")
DB_NAME = "database.db"
BASE_URL = "https://books.toscrape.com/"


def init_db():
    with sqlite3.connect(DB_NAME) as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            price REAL NOT NULL,
            availability TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'Unknown',
            page INTEGER NOT NULL DEFAULT 1
        )""")

       

        conn.commit()

init_db()


def fetch_categories():
    response = requests.get(BASE_URL, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcademicPipeline/1.0"})
    if response.status_code != 200:
        return []

    soup = BeautifulSoup(response.text, "html.parser")
    category_links = soup.select(".side_categories ul li ul li a")
    categories = []

    for link in category_links:
        name = link.text.strip()
        href = link.get("href", "").strip()
        if not href:
            continue
        normalized = href
        if normalized.endswith("index.html"):
            normalized = normalized[: -len("index.html")]
        normalized = normalized.rstrip("/")
        slug = normalized.split("/")[-1]
        categories.append({"name": name, "slug": slug})

    return categories


def build_category_page_url(category_slug: str, page: int):
    category_path = f"catalogue/category/books/{category_slug}"
    if page <= 1:
        return urljoin(BASE_URL, f"{category_path}/index.html")
    return urljoin(BASE_URL, f"{category_path}/page-{page}.html")


def run_scraper_engine(category_slug: str = "travel_2", page: int = 1):
    url = build_category_page_url(category_slug, page)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AcademicPipeline/1.0"}

    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        return False

    soup = BeautifulSoup(response.text, "html.parser")
    book_pods = soup.find_all("article", class_="product_pod")
    if not book_pods:
        return False

    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()

        for pod in book_pods:
            title = pod.h3.a["title"]
            price_text = pod.find("p", class_="price_color").text
            price = float(price_text.replace("£", "").replace("Â", ""))
            availability = pod.find("p", class_="instock availability").text.strip()

            exists = cursor.execute(
                "SELECT 1 FROM books WHERE title = ? AND category = ? AND page = ?",
                (title, category_slug, page)
            ).fetchone()
            if not exists:
                cursor.execute(
                    "INSERT INTO books (title, price, availability, category, page) VALUES (?, ?, ?, ?, ?)",
                    (title, price, availability, category_slug, page)
                )
        conn.commit()

    return True


@app.post("/api/scrape")
def trigger_scrape(category: str = Query("travel_2"), page: int = Query(1, ge=1)):
    success = run_scraper_engine(category, page)
    if not success:
        return {"status": "error", "message": "Failed to fetch data from target server or no books found."}
    return {"status": "success", "message": "Scraper executed successfully! Database updated."}


@app.get("/api/categories")
def get_categories():
    return fetch_categories()


@app.get("/api/books")
def get_books(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50)
):
    offset = (page - 1) * page_size
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM books"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)

        count_query = query.replace("SELECT *", "SELECT COUNT(*)")
        total_count = conn.execute(count_query, params).fetchone()[0]

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        rows = conn.execute(query, params).fetchall()

    total_pages = max(1, math.ceil(total_count / page_size))
    return {
        "books": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "total_count": total_count,
    }


@app.get("/api/books/csv")
def download_books_csv(
    category: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50)
):
    offset = (page - 1) * page_size
    with sqlite3.connect(DB_NAME) as conn:
        conn.row_factory = sqlite3.Row
        query = "SELECT * FROM books"
        params = []
        if category:
            query += " WHERE category = ?"
            params.append(category)

        query += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params.extend([page_size, offset])
        rows = conn.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["id", "title", "price", "availability", "category", "page"])
    for row in rows:
        writer.writerow([row["id"], row["title"], row["price"], row["availability"], row["category"], row["page"]])
    output.seek(0)

    filename = f"books_{category or 'all'}_p{page}.csv"
    return StreamingResponse(
        output,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=\"{filename}\""}
    )


app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def home():
    return FileResponse("static/index.html")





