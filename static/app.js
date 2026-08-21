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