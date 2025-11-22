import os
import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, Form, UploadFile, HTTPException
import datetime

cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("CLOUD_API_KEY"),
    api_secret=os.getenv("CLOUD_API_SECRET")
)

app = FastAPI(title="NiqueeBackend")

@app.get("/")
def read_root():
    return {"msg": "Backend Niquee funcionando"}

@app.post("/upload")
def upload_file(user: str = Form(...), file: UploadFile = File(...)):
    if file.content_type not in ["image/jpeg", "image/png", "application/pdf"]:
        raise HTTPException(400, detail="Formato no permitido")
    res = cloudinary.uploader.upload(file.file, resource_type="auto")
    return {"url": res["secure_url"], "name": file.filename}