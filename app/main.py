from fastapi import FastAPI, Depends, HTTPException, status, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.openapi.utils import get_openapi

from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError


from urllib.parse import quote_plus
from datetime import timedelta, datetime
import secrets

from jose import JWTError, jwt

from .database import Base, engine, get_db
from .models import User, Patient, Consultation
from .schemas import (
    RegisterUser, UserOut, LoginRequest, TokenResponse,
    PatientCreate, PatientOut, AssignPatientRequest,
    ScheduleConsultationRequest, ConsultationOut,
    ConsultationShareRequest, ConsultationShareResponse, WhatsAppLinkResponse
)
from .utils import (
    hash_password, verify_password, create_access_token,
    SECRET_KEY, ALGORITHM
)

# -------------------- App & CORS --------------------
app = FastAPI(
    title="Prakvedaa CRM API",
    version="0.1.0",
    swagger_ui_parameters={"persistAuthorization": True},  # keep token in UI
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------- Security --------------------
bearer_scheme = HTTPBearer(auto_error=False)

def get_current_user(
    creds: HTTPAuthorizationCredentials = Security(bearer_scheme),
    db: Session = Depends(get_db),
):
    if not creds or not creds.scheme:
        raise HTTPException(status_code=401, detail="Missing or invalid token")

    # HTTPBearer usually provides only the token, but clean defensively.
    token = (creds.credentials or "").strip()
    if token.lower().startswith("bearer "):
        # Handle odd cases like "Bearer Bearer <token>"
        token = token.split()[-1]

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_email: str | None = payload.get("sub")
        if not user_email:
            raise HTTPException(status_code=401, detail="Invalid token payload")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

    user = db.query(User).filter(User.email == user_email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Show a single global 🔒 Authorize button
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description="Prakvedaa CRM API with JWT Auth",
        routes=app.routes,
    )
    schema.setdefault("components", {})
    schema["components"]["securitySchemes"] = {
        "HTTPBearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
    }
    schema["security"] = [{"HTTPBearer": []}]
    app.openapi_schema = schema
    return app.openapi_schema

app.openapi = custom_openapi

# -------------------- Lifecycle --------------------
@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)

# -------------------- Health --------------------
@app.get("/health")
def health():
    return {"status": "ok"}

# -------------------- Auth --------------------
@app.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterUser, db: Session = Depends(get_db)):
    user = User(
        name=payload.name,
        email=payload.email.lower().strip(),
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="Email already registered")
    return user

@app.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == payload.email.lower().strip()).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid email or password")

    access_token = create_access_token(
        data={"sub": user.email, "role": user.role},
        expires_delta=timedelta(minutes=60),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "authorization": f"Bearer {access_token}",  # ready-to-copy for Swagger
    }

# -------------------- Patients --------------------
@app.post("/patients/create", response_model=PatientOut)
def create_patient(
    payload: PatientCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.role != "sales":
        raise HTTPException(status_code=403, detail="Only sales role can create patients")

    patient = Patient(
        name=payload.name,
        age=payload.age,
        contact=payload.contact,
        notes=payload.notes,
        created_by=current_user.email,
    )
    db.add(patient)
    db.commit()
    db.refresh(patient)
    return patient

@app.get("/patients/list", response_model=list[PatientOut])
def list_patients(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Sales sees all; Doctor sees only assigned to them
    if current_user.role == "sales":
        patients = db.query(Patient).order_by(Patient.id.desc()).all()
    elif current_user.role == "doctor":
        patients = (
            db.query(Patient)
            .filter(Patient.assigned_doctor_email == current_user.email)
            .order_by(Patient.id.desc())
            .all()
        )
    else:
        raise HTTPException(status_code=403, detail="Role not permitted")
    return patients

@app.post("/patients/assign", response_model=PatientOut)
def assign_patient(
    payload: AssignPatientRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if current_user.role != "sales":
        raise HTTPException(status_code=403, detail="Only sales can assign patients")

    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # validate doctor exists & role
    doctor = db.query(User).filter(User.email == payload.doctor_email.lower().strip()).first()
    if not doctor or doctor.role != "doctor":
        raise HTTPException(status_code=400, detail="Doctor email invalid or not a doctor")

    patient.assigned_doctor_email = doctor.email
    db.commit()
    db.refresh(patient)
    return patient

# -------------------- Consultations --------------------
@app.post("/consultations/schedule", response_model=ConsultationOut)
def schedule_consultation(
    payload: ScheduleConsultationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    patient = db.query(Patient).filter(Patient.id == payload.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    # Sales can schedule for any; Doctor only for assigned patients
    if current_user.role == "doctor" and patient.assigned_doctor_email != current_user.email:
        raise HTTPException(status_code=403, detail="Doctor not assigned to this patient")
    if current_user.role not in ["sales", "doctor"]:
        raise HTTPException(status_code=403, detail="Not allowed to schedule consultations")

    room_name = f"Prakvedaa-{secrets.token_urlsafe(6)}"
    video_url = f"https://meet.jit.si/{room_name}"

    consultation = Consultation(
        patient_id=patient.id,
        scheduled_at=payload.scheduled_at,
        video_url=video_url,
        created_by=current_user.email
    )
    db.add(consultation)
    db.commit()
    db.refresh(consultation)
    return consultation

@app.get("/consultations/list", response_model=list[ConsultationOut])
def list_consultations(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Sales → sees all consultations.
    Doctor → sees consultations for patients assigned to that doctor only.
    """
    if current_user.role == "sales":
        consultations = db.query(Consultation).order_by(Consultation.id.desc()).all()
        return consultations

    if current_user.role == "doctor":
        consultations = (
            db.query(Consultation)
            .join(Patient, Patient.id == Consultation.patient_id)
            .filter(Patient.assigned_doctor_email == current_user.email)
            .order_by(Consultation.id.desc())
            .all()
        )
        return consultations

    raise HTTPException(status_code=403, detail="Role not permitted")

# -------------------- Sharing (message + WhatsApp link) --------------------
@app.post("/consultations/share-message", response_model=ConsultationShareResponse)
def share_message(
    payload: ConsultationShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cons = db.query(Consultation).filter(Consultation.id == payload.consultation_id).first()
    if not cons:
        raise HTTPException(status_code=404, detail="Consultation not found")

    patient = db.query(Patient).filter(Patient.id == cons.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if current_user.role == "doctor" and patient.assigned_doctor_email != current_user.email:
        raise HTTPException(status_code=403, detail="Not allowed to share this consultation")

    when_str = cons.scheduled_at.isoformat() if cons.scheduled_at else "Now"
    doc_str = patient.assigned_doctor_email or "TBD"

    msg = (
        f"Hello {patient.name}, your video consultation is scheduled.\n"
        f"🔗 Link: {cons.video_url}\n"
        f"👨‍⚕️ Doctor: {doc_str}\n"
        f"🕒 Time: {when_str}\n"
        f"— Sent by {current_user.email}"
    )
    return ConsultationShareResponse(message=msg)

@app.post("/consultations/whatsapp-link", response_model=WhatsAppLinkResponse)
def whatsapp_link(
    payload: ConsultationShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cons = db.query(Consultation).filter(Consultation.id == payload.consultation_id).first()
    if not cons:
        raise HTTPException(status_code=404, detail="Consultation not found")

    patient = db.query(Patient).filter(Patient.id == cons.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if current_user.role == "doctor" and patient.assigned_doctor_email != current_user.email:
        raise HTTPException(status_code=403, detail="Not allowed to share this consultation")

    when_str = cons.scheduled_at.isoformat() if cons.scheduled_at else "Now"
    doc_str = patient.assigned_doctor_email or "TBD"

    msg = (
        f"Hello {patient.name}, your video consultation is scheduled.\n"
        f"Link: {cons.video_url}\n"
        f"Doctor: {doc_str}\n"
        f"Time: {when_str}"
    )
    encoded = quote_plus(msg)

    phone = None
    if hasattr(payload, "phone_e164") and payload.phone_e164:
        phone = payload.phone_e164
    elif patient.contact:
        phone = patient.contact.replace("+", "").replace(" ", "")

    if not phone:
        raise HTTPException(status_code=400, detail="No phone provided and patient.contact empty")

    wa = f"https://wa.me/{phone}?text={encoded}"
    return WhatsAppLinkResponse(wa_link=wa)

@app.post("/consultations/send-whatsapp", response_model=WhatsAppLinkResponse)
def whatsapp_send_direct(
    payload: ConsultationShareRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    cons = db.query(Consultation).filter(Consultation.id == payload.consultation_id).first()
    if not cons:
        raise HTTPException(status_code=404, detail="Consultation not found")

    patient = db.query(Patient).filter(Patient.id == cons.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    if current_user.role == "doctor" and patient.assigned_doctor_email != current_user.email:
        raise HTTPException(status_code=403, detail="Not allowed to share this consultation")

    when_str = cons.scheduled_at.isoformat() if cons.scheduled_at else "Now"
    doc_str = patient.assigned_doctor_email or "TBD"

    msg = (
        f"Hello {patient.name}, your video consultation is scheduled.\n"
        f"Link: {cons.video_url}\n"
        f"Doctor: {doc_str}\n"
        f"Time: {when_str}"
    )
    encoded = quote_plus(msg)

    phone = None
    if hasattr(payload, "phone_e164") and payload.phone_e164:
        phone = payload.phone_e164
    elif patient.contact:
        phone = patient.contact.replace("+", "").replace(" ", "")

    if not phone:
        raise HTTPException(status_code=400, detail="No phone provided and patient.contact empty")

    # ✅ Final one-click redirect link
    wa = f"https://wa.me/{phone}?text={encoded}"
    return WhatsAppLinkResponse(wa_link=wa)

# --- Users (list, optional role filter) ---
from typing import Optional
from fastapi import Query

@app.get("/users", response_model=list[UserOut])
def list_users(
    role: Optional[str] = Query(None, description="Filter by role, e.g. 'doctor' or 'sales'"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(User)
    if role:
        q = q.filter(User.role == role)
    return q.order_by(User.id.desc()).all()
from fastapi import  Body

@app.patch("/consultations/update", response_model=ConsultationOut)
def update_consultation(
    consultation_id: int,
    notes: str = Body(None, embed=True),
    status: str = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    if not consultation:
        raise HTTPException(status_code=404, detail="Consultation not found")

    # ✅ Allow Doctor assigned OR Sales to update
    patient = db.query(Patient).filter(Patient.id == consultation.patient_id).first()
    if current_user.role == "doctor" and patient.assigned_doctor_email != current_user.email:
        raise HTTPException(status_code=403, detail="Not allowed to update this consultation")

    # ✅ Save doctor notes if provided
    if notes is not None:
        consultation.doctor_notes = notes.strip() if notes else consultation.doctor_notes

    # ✅ Save status if provided ("completed" or "pending")
    if status is not None:
        consultation.status = status.lower()

    db.commit()
    db.refresh(consultation)  # ✅ returns updated object

    db.refresh(consultation)
    return consultation  # ✅ This ensures status + notes go to frontend


# -------------------- Dev runner --------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
