import os
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from uuid import uuid4

from database import db, create_document, get_documents
from schemas import Transaction, Recurring, Share

app = FastAPI(title="508 Spendings API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "508 Spendings API Running"}


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


# Helper

def collection_name(model_cls):
    return model_cls.__name__.lower()


# Input models for endpoints

class TransactionIn(BaseModel):
    client_id: str
    amount: float
    category: str
    note: Optional[str] = None
    type: str  # "income" | "expense"
    date: Optional[datetime] = None


class RecurringIn(BaseModel):
    client_id: str
    label: str
    amount: float
    category: str
    frequency: str  # daily|weekly|monthly
    type: str  # income|expense
    next_due_date: Optional[datetime] = None


class ShareCreateIn(BaseModel):
    client_id: str


@app.post("/api/transactions")
def create_transaction(payload: TransactionIn):
    # Normalize sign based on type
    amt = abs(payload.amount)
    if payload.type == "expense":
        amt = -amt

    tx = Transaction(
        client_id=payload.client_id,
        amount=amt,
        category=payload.category,
        note=payload.note,
        date=payload.date or datetime.now(timezone.utc),
        type="income" if amt >= 0 else "expense",
    )
    inserted_id = create_document(collection_name(Transaction), tx)
    return {"id": inserted_id}


@app.get("/api/transactions")
def list_transactions(client_id: str, category: Optional[str] = None, limit: int = 200):
    filt = {"client_id": client_id}
    if category:
        filt["category"] = category
    docs = get_documents(collection_name(Transaction), filt, limit)
    # Convert ObjectId and datetime to serializable
    for d in docs:
        d["_id"] = str(d.get("_id"))
        if isinstance(d.get("date"), datetime):
            d["date"] = d["date"].isoformat()
        if isinstance(d.get("created_at"), datetime):
            d["created_at"] = d["created_at"].isoformat()
        if isinstance(d.get("updated_at"), datetime):
            d["updated_at"] = d["updated_at"].isoformat()
    # Sort by date desc
    docs.sort(key=lambda x: x.get("date", ""), reverse=True)
    return {"items": docs}


@app.get("/api/balance")
def get_balance(client_id: str):
    docs = get_documents(collection_name(Transaction), {"client_id": client_id})
    balance = sum(d.get("amount", 0) for d in docs)
    return {"balance": balance}


@app.post("/api/recurring")
def create_recurring(payload: RecurringIn):
    rec = Recurring(
        client_id=payload.client_id,
        label=payload.label,
        amount=payload.amount,
        category=payload.category,
        frequency=payload.frequency,
        type=payload.type,
        next_due_date=payload.next_due_date or datetime.now(timezone.utc),
    )
    inserted_id = create_document(collection_name(Recurring), rec)
    return {"id": inserted_id}


@app.get("/api/recurring")
def list_recurring(client_id: str):
    docs = get_documents(collection_name(Recurring), {"client_id": client_id})
    for d in docs:
        d["_id"] = str(d.get("_id"))
        nd = d.get("next_due_date")
        if isinstance(nd, datetime):
            d["next_due_date"] = nd.isoformat()
    return {"items": docs}


@app.get("/api/reminders")
def reminders(client_id: str):
    # Show items whose next_due_date is in the past by up to a period
    now = datetime.now(timezone.utc)
    docs = get_documents(collection_name(Recurring), {"client_id": client_id})
    due = []
    for d in docs:
        nd = d.get("next_due_date")
        if isinstance(nd, datetime):
            nd_dt = nd
        else:
            try:
                nd_dt = datetime.fromisoformat(nd)
            except Exception:
                nd_dt = now
        if nd_dt <= now:
            due.append({"label": d.get("label"), "category": d.get("category"), "amount": d.get("amount")})
    return {"due": due}


@app.post("/api/share")
def create_share(payload: ShareCreateIn):
    token = uuid4().hex[:10]
    share = Share(client_id=payload.client_id, token=token, created_at=datetime.now(timezone.utc))
    inserted_id = create_document(collection_name(Share), share)
    return {"token": token}


@app.get("/api/share/{token}")
def get_shared_dashboard(token: str):
    # Find share by token
    docs = get_documents(collection_name(Share), {"token": token}, limit=1)
    if not docs:
        raise HTTPException(status_code=404, detail="Share not found")
    client_id = docs[0].get("client_id")
    # Fetch transactions and balance and categories breakdown
    txs = get_documents(collection_name(Transaction), {"client_id": client_id})
    balance = sum(t.get("amount", 0) for t in txs)
    by_cat = {}
    for t in txs:
        cat = t.get("category", "Uncategorized")
        by_cat.setdefault(cat, 0)
        by_cat[cat] += t.get("amount", 0)
    # Serialize
    items = []
    for t in txs:
        t["_id"] = str(t.get("_id"))
        if isinstance(t.get("date"), datetime):
            t["date"] = t["date"].isoformat()
        items.append(t)
    return {"client_id": client_id, "balance": balance, "items": items, "categories": by_cat}


# Simple category totals endpoint
@app.get("/api/categories")
def category_totals(client_id: str):
    txs = get_documents(collection_name(Transaction), {"client_id": client_id})
    by_cat = {}
    for t in txs:
        cat = t.get("category", "Uncategorized")
        by_cat.setdefault(cat, 0)
        by_cat[cat] += t.get("amount", 0)
    return {"categories": by_cat}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
