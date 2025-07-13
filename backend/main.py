from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import uvicorn
import os
import logging

from backend.scraper import GoogleScraper

# Initialize app
app = FastAPI()

# Enable CORS for frontend JS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount frontend directory
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

# Logger setup
logging.basicConfig(level=logging.INFO)

# Ensure output folder exists
os.makedirs("output", exist_ok=True)

# Serve frontend HTML
@app.get("/", response_class=HTMLResponse)
async def serve_index():
    try:
        with open("frontend/index.html", "r", encoding="utf-8") as f:
            html_content = f.read()
        return HTMLResponse(content=html_content)
    except Exception as e:
        logging.exception("Error loading index.html:")
        return JSONResponse(status_code=500, content={"error": "Frontend not found."})


# Scrape request schema
class ScrapeRequest(BaseModel):
    url: str
    num_reviews: int
    start_date: Optional[str] = None
    end_date: Optional[str] = None


# Scraping endpoint
@app.post("/scrape")
def scrape_reviews(req: ScrapeRequest):
    try:
        scraper = GoogleScraper()
        result = scraper.scrape_reviews(
            url=req.url,
            num_reviews=req.num_reviews,
            start_date=req.start_date,
            end_date=req.end_date,
        )

        file_name = os.path.basename(result["file_path"])
        download_link = f"/download/{file_name}"

        return {
            "place_name": result["place_name"],
            "download_link": download_link,
            "top_reviews": result["top_reviews"],
            "map_embed": result["map_embed"]
        }

    except Exception as e:
        logging.exception("❌ Error during scraping:")
        return JSONResponse(status_code=500, content={"error": str(e)})


# Download Excel file
@app.get("/download/{file_name}")
def download_file(file_name: str):
    # Path traversal protection
    if ".." in file_name or "/" in file_name or "\\" in file_name:
        return JSONResponse(status_code=400, content={"error": "Invalid filename"})

    file_path = os.path.join("output", file_name)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path,
            filename=file_name,
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    return JSONResponse(status_code=404, content={"error": "File not found"})


# Health check route
@app.get("/health")
def health_check():
    return {"status": "ok", "message": "Server is healthy 🚀"}


# Run using: uvicorn backend.main:app --reload
if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
