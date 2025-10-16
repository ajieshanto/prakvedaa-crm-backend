from pydantic import BaseModel, EmailStr, Field
from typing import Literal, Optional, List
from datetime import datetime


Role = Literal["sales", "doctor", "admin"]

class RegisterUser(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(..., min_length=6, max_length=128)
    role: Role = "sales"

class UserOut(BaseModel):
    id: int
    name: str
    email: EmailStr
    role: Role

    class Config:
        from_attributes = True
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    authorization: str  # ✅ Add this line

class PatientCreate(BaseModel):
    name: str
    age: int | None = None
    contact: str | None = None
    notes: str | None = None

class PatientOut(BaseModel):
    id: int
    name: str
    age: Optional[int]
    contact: Optional[str]
    notes: Optional[str]
    created_by: str
    assigned_doctor_email: Optional[EmailStr] = None

    class Config:
        from_attributes = True

# 👉 Create request model for assigning a doctor
class AssignPatientRequest(BaseModel):
    patient_id: int
    doctor_email: EmailStr

# 👉 Create model for creating patients (already have)
# class PatientCreate(BaseModel): ...  (keep your existing)

# 👉 Consultations
class ScheduleConsultationRequest(BaseModel):
    patient_id: int
    scheduled_at: Optional[datetime] = None  # ISO string in Swagger is fine

# ✅ Put this inside schemas.py, replacing your old ConsultationOut

class ConsultationOut(BaseModel):
    id: int
    patient_id: int
    scheduled_at: Optional[datetime]
    video_url: str
    created_by: str
    status: Optional[str] = "pending"           # 👈 NOW INCLUDED
    doctor_notes: Optional[str] = None          # 👈 NOW INCLUDED

    class Config:
        orm_mode = True  # ✅ This ensures ORM fields like doctor_notes/status are serialized


class ConsultationShareRequest(BaseModel):
    consultation_id: int
    # Optional: override the number used for WhatsApp deep link (otherwise uses patient.contact)
    phone_e164: Optional[str] = None  # e.g. "919876543210" (no +)

class ConsultationShareResponse(BaseModel):
    message: str  # nicely formatted message you can copy to WhatsApp/SMS

class WhatsAppLinkResponse(BaseModel):
    wa_link: str  # https://wa.me/<number>?text=<encoded>
