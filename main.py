
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="IT LearnBot Add-on Store",
    version="1.0.0",
    description="IT LearnBot qo‘shimchalar do‘koni API"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {
        "name": "IT LearnBot Add-on Store",
        "status": "online",
        "version": "1.0.0"
    }

@app.get("/api/addons")
def addons():
    return {
        "addons": [],
        "total": 0
    }

@app.get("/api/version")
def version():
    return {
        "version": "1.0.0"
    }
