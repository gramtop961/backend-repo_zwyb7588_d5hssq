import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson import ObjectId
from datetime import datetime

from database import db, create_document, get_documents
from schemas import Task

app = FastAPI(title="Christmas To-Do API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"message": "Christmas To-Do Backend is running!"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"
    return response

# Helper to convert MongoDB documents to serializable dict

def serialize_task(doc: dict) -> dict:
    if not doc:
        return {}
    doc["id"] = str(doc.pop("_id"))
    # Ensure datetime is ISO if present
    if "due_date" in doc and isinstance(doc["due_date"], datetime):
        doc["due_date"] = doc["due_date"].isoformat()
    if "created_at" in doc and isinstance(doc["created_at"], datetime):
        doc["created_at"] = doc["created_at"].isoformat()
    if "updated_at" in doc and isinstance(doc["updated_at"], datetime):
        doc["updated_at"] = doc["updated_at"].isoformat()
    return doc

class TaskCreate(BaseModel):
    title: str
    priority: Optional[str] = "medium"
    due_date: Optional[datetime] = None
    notes: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    completed: Optional[bool] = None
    priority: Optional[str] = None
    due_date: Optional[datetime] = None
    notes: Optional[str] = None

@app.get("/api/tasks")
def list_tasks() -> List[dict]:
    docs = get_documents("task", {}, limit=None)
    # sort by created_at desc
    docs = sorted(docs, key=lambda d: d.get("created_at", datetime.min), reverse=True)
    return [serialize_task(d) for d in docs]

@app.post("/api/tasks", status_code=201)
def create_task(payload: TaskCreate) -> dict:
    task = Task(
        title=payload.title,
        completed=False,
        priority=payload.priority or "medium",
        due_date=payload.due_date,
        notes=payload.notes,
    )
    new_id = create_document("task", task)
    doc = db["task"].find_one({"_id": ObjectId(new_id)})
    return serialize_task(doc)

@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, payload: TaskUpdate) -> dict:
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    update = {k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        return get_task(task_id)
    update["updated_at"] = datetime.utcnow()
    res = db["task"].update_one({"_id": ObjectId(task_id)}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    doc = db["task"].find_one({"_id": ObjectId(task_id)})
    return serialize_task(doc)

@app.delete("/api/tasks/{task_id}", status_code=204)
def delete_task(task_id: str):
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    res = db["task"].delete_one({"_id": ObjectId(task_id)})
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}

@app.post("/api/tasks/{task_id}/toggle")
def toggle_task(task_id: str) -> dict:
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = db["task"].find_one({"_id": ObjectId(task_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    new_val = not bool(doc.get("completed", False))
    db["task"].update_one({"_id": ObjectId(task_id)}, {"$set": {"completed": new_val, "updated_at": datetime.utcnow()}})
    doc = db["task"].find_one({"_id": ObjectId(task_id)})
    return serialize_task(doc)

@app.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict:
    if not ObjectId.is_valid(task_id):
        raise HTTPException(status_code=400, detail="Invalid task id")
    doc = db["task"].find_one({"_id": ObjectId(task_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Task not found")
    return serialize_task(doc)


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
