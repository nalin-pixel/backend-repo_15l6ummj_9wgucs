"""
Database Schemas

Define your MongoDB collection schemas here using Pydantic models.
These schemas are used for data validation in your application.

Each Pydantic model represents a collection in your database.
Model name is converted to lowercase for the collection name:
- User -> "user" collection
- Product -> "product" collection
- BlogPost -> "blogs" collection
"""

from pydantic import BaseModel, Field
from typing import Optional, Literal
from datetime import datetime

# 508 Spendings schemas

class Transaction(BaseModel):
    """
    Transactions collection schema
    Collection: "transaction"
    """
    client_id: str = Field(..., description="Anonymous client identifier")
    amount: float = Field(..., description="Positive for income, negative for expense")
    category: str = Field(..., description="Category for the transaction")
    note: Optional[str] = Field(None, description="Optional note")
    date: Optional[datetime] = Field(None, description="Datetime of the transaction; defaults to now on backend if not provided")
    type: Literal["income", "expense"] = Field(..., description="Type of transaction")

class Recurring(BaseModel):
    """
    Recurring payments/contributions
    Collection: "recurring"
    """
    client_id: str
    label: str
    amount: float = Field(..., description="Amount each recurrence. Positive for income/savings, negative for expense")
    category: str
    frequency: Literal["daily", "weekly", "monthly"] = "monthly"
    type: Literal["income", "expense"] = "income"
    next_due_date: Optional[datetime] = None

class Share(BaseModel):
    """
    Public share tokens mapping to a client_id
    Collection: "share"
    """
    client_id: str
    token: str
    created_at: Optional[datetime] = None
