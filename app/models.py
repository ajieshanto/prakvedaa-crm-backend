from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from .database import Base
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime


class User(Base):
    __tablename__ = "users"  # ✅ 4 SPACES INDENTED

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), nullable=False, default="sales")  # sales | doctor | admin
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

class Patient(Base):
    __tablename__ = "patients"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    age = Column(Integer, nullable=True)
    contact = Column(String(50), nullable=True)
    notes = Column(String(255), nullable=True)
    created_by = Column(String(255), nullable=False)
    assigned_doctor_email = Column(String(255), nullable=True)  # 👈 NEW
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

# ✅ FINAL Consultation Model (Keep ONLY this one)
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from datetime import datetime

class Consultation(Base):
    __tablename__ = "consultations"
    __table_args__ = {'extend_existing': True}  # prevents metadata clash

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.id"), nullable=False)
    video_url = Column(String(255), nullable=False)
    scheduled_at = Column(DateTime, nullable=True)   # ISO parsed automatically
    created_by = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")   # pending | completed
    doctor_notes = Column(Text, nullable=True)       # doctor's final notes/prescription
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

