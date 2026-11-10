
import json
import urllib.request
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="IT LearnBot Add-on Store",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

GITHUB_CATALOG = (
    "https://raw.githubusercontent.com/"
    "abduxoliq0987-cmyk/it-learnbot-addon-store/"
    "main/addons.json"
)

def get_catalog():
    request = urllib.request.Request(
        GITHUB_CATALOG,
        headers={"User-Agent": "IT-LearnBot-Store"}
    )

    with urllib.request.urlopen(request, timeout=15) as response:
        data = json.loads(response.read().decode("utf-8"))

    if not isinstance(data.get("addons"), list):
        raise ValueError("Noto'g'ri katalog formati")

    return data

@app.get("/")
def home():
    return {
        "name": "IT LearnBot Add-on Store",
        "status": "online",
        "version": "1.1.0"
    }

@app.get("/api/addons")
def addons():
    try:
        catalog = get_catalog()
        return {
            "store_name": catalog.get(
                "store_name", "IT LearnBot Add-on Store"
            ),
            "version": catalog.get("version", "1.0.0"),
            "addons": catalog["addons"],
            "total": len(catalog["addons"])
        }
    except Exception as error:
        return {
            "error": "Katalogni yuklab bo'lmadi",
            "details": str(error),
            "addons": [],
            "total": 0
        }

@app.get("/api/version")
def version():
    return {"version": "1.1.0"}
