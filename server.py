
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





<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Books WebScraper</title>
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <div class="layout-wrapper">
        <!-- Control Panel Sidebar -->
        <div class="sidebar">
            <h2>DASHBOARD</h2>
            <p>Select a category, navigate pages, and trigger live scraping directly from the browser.</p>
            <h2>Enjoy Reading!</h2>
            <label for="categorySelect" class="sidebar-label">Category</label>
            <select id="categorySelect" class="category-select"></select>
            <div class="pagination-controls">
                <button id="prevPageBtn" class="btn-page">← Prev</button>
                <span id="pageIndicator">Page 1</span>
                <button id="nextPageBtn" class="btn-page">Next →</button>
            </div>
            <button id="scrapeBtn" class="btn-scrape">🚀 Run Web Scraper</button>
            <button id="downloadCsvBtn" class="btn-download">⬇️ Download CSV file</button>
            <div id="statusIndicator" class="status-text">System Ready</div>
        </div>

        <!-- Main Analytics Window -->
        <div class="main-panel">
            <h1>Welcome to Book Scraper</h1>
            <h3>Sleep is good, but books are better</h3>
            <div class="card">
                <table>
                    <thead>
                        <tr>
                            <th>ID</th>
                            <th>Book Title</th>
                            <th>Price (USD)</th>
                            <th>Stock</th>
                        </tr>
                    </thead>
                    <tbody id="dataGrid">
                        <!-- Content dynamically appended here -->
                    </tbody>
                </table>
            </div>
        </div>
    </div>
    <script src="/static/app.js"></script>
</body>
</html>


body {
    font-family: 'Segoe UI', Arial, sans-serif;
    margin: 0;
    background-color: #f8fafc;
}
.layout-wrapper {
    display: flex;
    height: 100vh;
}
.sidebar {
    width: 320px;
    background-color: #0f172a;
    padding: 30px 24px;
    color: #94a3b8;
    font-size: 0.9rem;
}
.sidebar h2 { color: #f8fafc; margin-top: 0; font-size: 1.3rem;}
.sidebar-label {
    display: block;
    margin-top: 20px;
    color: #cbd5e1;
    font-size: 0.95rem;
    margin-bottom: 8px;
}
.category-select {
    width: 100%;
    padding: 12px;
    border-radius: 8px;
    border: 1px solid #334155;
    background-color: #0f172a;
    color: #f8fafc;
}
.pagination-controls {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-top: 18px;
}
.btn-page {
    flex: 1;
    padding: 12px;
    background-color: #1d4ed8;
    color: #fff;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    transition: background 0.2s;
}
.btn-page:hover:not(:disabled) {
    background-color: #2563eb;
}
.btn-page:disabled {
    background-color: #475569;
    cursor: not-allowed;
}
#pageIndicator {
    flex: 1;
    text-align: center;
    color: #e2e8f0;
    font-weight: 600;
}
.btn-scrape,
.btn-download {
    width: 100%;
    padding: 14px;
    color: #0f172a;
    font-weight: bold;
    font-size: 0.95rem;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    transition: background 0.2s;
    margin-top: 20px;
}
.btn-scrape { background-color: #38bdf8; }
.btn-scrape:hover { background-color: #7dd3fc; }
.btn-download { background-color: #34d399; }
.btn-download:hover { background-color: #6ee7b7; }
.status-text {
    margin-top: 15px;
    text-align: center;
    font-weight: bold;
    color: #38bdf8;
}
.main-panel {
    flex-grow: 1;
    padding: 40px;
    overflow-y: auto;
}
.card {
    background: white;
    padding: 24px;
    border-radius: 8px;
    box-shadow: 0 4px 6px -1px rgb(0 0 0 / 0.05);
}
table { width: 100%; border-collapse: collapse; }
th, td { padding: 14px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }
th { color: #64748b; font-size: 0.85rem; text-transform: uppercase; letter-spacing: 0.05em; }
td { color: #334155; }



document.addEventListener("DOMContentLoaded", () => {
    const dataGrid = document.getElementById("dataGrid");
    const categorySelect = document.getElementById("categorySelect");
    const scrapeBtn = document.getElementById("scrapeBtn");
    const downloadCsvBtn = document.getElementById("downloadCsvBtn");
    const statusIndicator = document.getElementById("statusIndicator");
    const prevPageBtn = document.getElementById("prevPageBtn");
    const nextPageBtn = document.getElementById("nextPageBtn");
    const pageIndicator = document.getElementById("pageIndicator");

    let currentCategory = "travel_2";
    let currentPage = 1;
    let totalPages = 1;

    async function fetchCategories() {
        const response = await fetch("/api/categories");
        const categories = await response.json();

        categorySelect.innerHTML = "";
        categories.forEach(category => {
            const option = document.createElement("option");
            option.value = category.slug;
            option.textContent = category.name;
            categorySelect.appendChild(option);
        });

        if (categories.length > 0) {
            currentCategory = categories[0].slug;
            categorySelect.value = currentCategory;
        }
    }

    async function refreshDataGrid() {
        const response = await fetch(`/api/books?category=${encodeURIComponent(currentCategory)}&page=${currentPage}`);
        const data = await response.json();
        const books = data.books || [];

        totalPages = data.total_pages || 1;
        pageIndicator.innerText = `Page ${currentPage} of ${totalPages}`;
        updatePaginationState();

        dataGrid.innerHTML = "";

        if (books.length === 0) {
            dataGrid.innerHTML = `<tr><td colspan="4" style="text-align:center; color:#94a3b8;">No data for this category/page. Run the scraper or choose another category.</td></tr>`;
            return;
        }

        books.forEach(book => {
            const row = `
                <tr>
                    <td><strong>#${book.id}</strong></td>
                    <td>${book.title}</td>
                    <td>$${book.price.toFixed(2)}</td>
                    <td><span style="color: #16a34a; font-weight:bold;">${book.availability}</span></td>
                </tr>
            `;
            dataGrid.insertAdjacentHTML("beforeend", row);
        });
    }

    function updatePaginationState() {
        prevPageBtn.disabled = currentPage <= 1;
        nextPageBtn.disabled = currentPage >= totalPages;
    }

    categorySelect.addEventListener("change", async () => {
        currentCategory = categorySelect.value;
        currentPage = 1;
        await refreshDataGrid();
    });

    prevPageBtn.addEventListener("click", async () => {
        if (currentPage > 1) {
            currentPage -= 1;
            await refreshDataGrid();
        }
    });

    nextPageBtn.addEventListener("click", async () => {
        if (currentPage < totalPages) {
            currentPage += 1;
            await refreshDataGrid();
        }
    });

    scrapeBtn.addEventListener("click", async () => {
        scrapeBtn.disabled = true;
        statusIndicator.innerText = "⏳ Scraping live site...";
        statusIndicator.style.color = "#fbbf24";

        try {
            const response = await fetch(`/api/scrape?category=${encodeURIComponent(currentCategory)}&page=${currentPage}`, { method: "POST" });
            const result = await response.json();

            if (result.status === "success") {
                statusIndicator.innerText = "✓ DB Updated!";
                statusIndicator.style.color = "#4ade80";
                await refreshDataGrid();
            } else {
                statusIndicator.innerText = " Scraper Error";
                statusIndicator.style.color = "#f87171";
            }
        } catch (error) {
            statusIndicator.innerText = " Connection Failed";
            statusIndicator.style.color = "#f87171";
        } finally {
            setTimeout(() => {
                scrapeBtn.disabled = false;
                statusIndicator.innerText = "System Ready";
                statusIndicator.style.color = "#38bdf8";
            }, 3000);
        }
    });

    downloadCsvBtn.addEventListener("click", () => {
        const url = `/api/books/csv?category=${encodeURIComponent(currentCategory)}&page=${currentPage}`;
        window.location.href = url;
    });

    async function init() {
        await fetchCategories();
        await refreshDataGrid();
    }

    init();
});

