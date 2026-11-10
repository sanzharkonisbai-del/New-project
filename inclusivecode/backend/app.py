"""InclusiveCode demo API. Python snippets are deliberately never executed here."""
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, String, Integer, Boolean, DateTime, ForeignKey, Text, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

DATABASE_URL = os.getenv("INCLUSIVECODE_DATABASE", "sqlite:///./inclusivecode.db")
SECRET_KEY = os.getenv("INCLUSIVECODE_SECRET", "dev-only-change-this-secret-before-deployment")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

class Base(DeclarativeBase): pass
class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20), default="student")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Lesson(Base):
    __tablename__ = "lessons"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(140))
    level: Mapped[str] = mapped_column(String(30), default="Жеңіл")
    content: Mapped[str] = mapped_column(Text, default="")
class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180))
    topic: Mapped[str] = mapped_column(String(100))
    level: Mapped[str] = mapped_column(String(30))
    prompt: Mapped[str] = mapped_column(Text)
class StudentResult(Base):
    __tablename__ = "student_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_id: Mapped[Optional[int]] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    lesson_title: Mapped[str] = mapped_column(String(140))
    score: Mapped[int] = mapped_column(Integer)
    completed: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class Assignment(Base):
    __tablename__ = "assignments"
    id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    student_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
class LearningProgress(Base):
    __tablename__ = "learning_progress"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    completed_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, default=0)
    difficulty: Mapped[str] = mapped_column(String(30), default="Жеңіл")
class AccessibilitySettings(Base):
    __tablename__ = "accessibility_settings"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    font_size: Mapped[int] = mapped_column(Integer, default=16)
    contrast: Mapped[bool] = mapped_column(Boolean, default=False)
    dark_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    simple_mode: Mapped[bool] = mapped_column(Boolean, default=False)

Base.metadata.create_all(engine)
app = FastAPI(title="InclusiveCode API", version="1.0.0", description="Inclusive Python learning demo API")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("INCLUSIVECODE_ORIGINS", "http://localhost:5173").split(","), allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
def db():
    session = SessionLocal()
    try: yield session
    finally: session.close()
def current_user(token: str | None = Depends(oauth), session: Session = Depends(db)):
    if not token: raise HTTPException(401, "Кіру қажет")
    try: user_id = int(jwt.decode(token, SECRET_KEY, algorithms=["HS256"])["sub"])
    except (JWTError, ValueError, KeyError): raise HTTPException(401, "Кіру мерзімі аяқталды")
    user = session.get(User, user_id)
    if not user: raise HTTPException(401, "Пайдаланушы табылмады")
    return user
def require_teacher(user: User = Depends(current_user)):
    if user.role != "teacher": raise HTTPException(403, "Бұл бөлім мұғалімдерге арналған")
    return user
def token_for(user: User): return jwt.encode({"sub": str(user.id), "exp": datetime.now(timezone.utc) + timedelta(hours=12)}, SECRET_KEY, algorithm="HS256")
class Register(BaseModel): name: str = Field(min_length=2, max_length=100); email: str; password: str = Field(min_length=8); role: str = "student"
class ResultIn(BaseModel): lesson_title: str; score: int = Field(ge=0, le=100); task_id: int | None = None; completed: bool = True
class TaskIn(BaseModel): title: str; topic: str; level: str; prompt: str; student_id: int | None = None
class SettingsIn(BaseModel): font_size: int = Field(default=16, ge=13, le=24); contrast: bool = False; dark_mode: bool = False; simple_mode: bool = False
@app.get("/api/health")
def health(): return {"status": "ok", "message": "InclusiveCode API жұмыс істеп тұр"}
@app.post("/api/auth/register")
def register(body: Register, session: Session = Depends(db)):
    email = body.email.strip().lower()
    if body.role not in ("student", "teacher"): raise HTTPException(422, "Рөл student немесе teacher болуы керек")
    if session.scalar(select(User).where(User.email == email)): raise HTTPException(409, "Бұл email тіркелген")
    user = User(name=body.name.strip(), email=email, password_hash=pwd.hash(body.password), role=body.role)
    session.add(user); session.flush(); session.add(LearningProgress(user_id=user.id)); session.add(AccessibilitySettings(user_id=user.id)); session.commit()
    return {"access_token": token_for(user), "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}
@app.post("/api/auth/token")
def login(form: OAuth2PasswordRequestForm = Depends(), session: Session = Depends(db)):
    user = session.scalar(select(User).where(User.email == form.username.strip().lower()))
    if not user or not pwd.verify(form.password, user.password_hash): raise HTTPException(401, "Email немесе құпиясөз қате")
    return {"access_token": token_for(user), "token_type": "bearer"}
@app.get("/api/me")
def me(user: User = Depends(current_user)): return {"id": user.id, "name": user.name, "email": user.email, "role": user.role}
@app.get("/api/lessons")
def lessons(session: Session = Depends(db)):
    if not session.scalar(select(Lesson.id).limit(1)):
        for title, level in [("Python негіздері","Жеңіл"),("Айнымалылар","Жеңіл"),("Мәліметтер типтері","Жеңіл"),("Шартты операторлар","Орташа"),("For циклі","Жеңіл"),("While циклі","Орташа"),("Тізімдер","Орташа"),("Функциялар","Күрделі"),("Қарапайым алгоритмдер","Күрделі")]: session.add(Lesson(title=title, level=level))
        session.commit()
    return [{"id": x.id, "title": x.title, "level": x.level} for x in session.scalars(select(Lesson))]
@app.post("/api/results")
def save_result(body: ResultIn, session: Session = Depends(db), user: User = Depends(current_user)):
    row = StudentResult(user_id=user.id, **body.model_dump()); session.add(row)
    progress = session.scalar(select(LearningProgress).where(LearningProgress.user_id == user.id))
    if not progress: progress = LearningProgress(user_id=user.id); session.add(progress)
    progress.completed_count += int(body.completed)
    progress.correct_streak = progress.correct_streak + 1 if body.score >= 70 else 0
    progress.difficulty = "Күрделі" if progress.correct_streak >= 3 else "Жеңіл" if body.score < 50 else "Орташа"
    session.commit()
    return {"saved": True, "result_id": row.id, "adaptive_level": progress.difficulty, "message": "Нәтиже сақталды"}
@app.get("/api/progress")
def progress(session: Session = Depends(db), user: User = Depends(current_user)):
    p = session.scalar(select(LearningProgress).where(LearningProgress.user_id == user.id))
    results = list(session.scalars(select(StudentResult).where(StudentResult.user_id == user.id).order_by(StudentResult.created_at.desc()).limit(20)))
    return {"completed_count": p.completed_count if p else 0, "correct_streak": p.correct_streak if p else 0, "next_difficulty": p.difficulty if p else "Жеңіл", "results": [{"lesson_title": r.lesson_title, "score": r.score, "created_at": r.created_at.isoformat()} for r in results]}
@app.get("/api/accessibility")
def get_settings(session: Session = Depends(db), user: User = Depends(current_user)):
    s = session.scalar(select(AccessibilitySettings).where(AccessibilitySettings.user_id == user.id)); return {"font_size": s.font_size, "contrast": s.contrast, "dark_mode": s.dark_mode, "simple_mode": s.simple_mode} if s else {}
@app.put("/api/accessibility")
def put_settings(body: SettingsIn, session: Session = Depends(db), user: User = Depends(current_user)):
    s = session.scalar(select(AccessibilitySettings).where(AccessibilitySettings.user_id == user.id))
    if not s: s = AccessibilitySettings(user_id=user.id); session.add(s)
    for key, value in body.model_dump().items(): setattr(s, key, value)
    session.commit(); return {"saved": True, **body.model_dump()}
@app.get("/api/teacher/students")
def students(session: Session = Depends(db), _: User = Depends(require_teacher)):
    users = list(session.scalars(select(User).where(User.role == "student")))
    return [{"id": u.id, "name": u.name, "email": u.email, "completed_count": (session.scalar(select(LearningProgress).where(LearningProgress.user_id == u.id)) or LearningProgress(user_id=u.id)).completed_count, "recent_results": [{"lesson_title": r.lesson_title, "score": r.score, "created_at": r.created_at.isoformat()} for r in session.scalars(select(StudentResult).where(StudentResult.user_id == u.id).order_by(StudentResult.created_at.desc()).limit(5))]} for u in users]
@app.post("/api/teacher/tasks")
def create_task(body: TaskIn, session: Session = Depends(db), teacher: User = Depends(require_teacher)):
    task = Task(title=body.title, topic=body.topic, level=body.level, prompt=body.prompt); session.add(task); session.flush()
    if body.student_id:
        if not session.get(User, body.student_id): raise HTTPException(404, "Оқушы табылмады")
        session.add(Assignment(teacher_id=teacher.id, student_id=body.student_id, task_id=task.id))
    session.commit(); return {"id": task.id, "title": task.title, "assigned": body.student_id is not None}
@app.get("/api/tasks")
def task_list(session: Session = Depends(db), user: User = Depends(current_user)):
    if user.role == "teacher": rows = list(session.scalars(select(Task)))
    else:
        assigned = select(Assignment.task_id).where(Assignment.student_id == user.id)
        rows = list(session.scalars(select(Task).where(Task.id.in_(assigned))))
    return [{"id": t.id, "title": t.title, "topic": t.topic, "level": t.level, "prompt": t.prompt} for t in rows]
@app.post("/api/assistant")
def assistant(body: dict):
    """Deterministic Kazakh fallback; replace with a server-side provider integration if configured."""
    q = str(body.get("question", "")).lower(); topic = str(body.get("topic", "Python"))
    if "қате" in q: answer = "Қате тұрған жолдағы айнымалы мен жақшаларды тексер. Әр жолды жеке орындап көр: қай жерде күткен мән өзгерді?"
    elif "цикл" in q or "for" in q: answer = "Цикл бір әрекетті қайталайды. range(1, 4) үш рет қадам жасайды: 1, 2, 3. Кодты қадамдап орындап көр!"
    elif "айнымалы" in q: answer = "Айнымалы — атауы бар қорап. Мысалы, ұпай = 5 деп мән сақтауға болады. Қай атауды пайдаланғың келеді?"
    else: answer = f"{topic}: кодты жол-жолымен оқып көр. Бірінші жол қандай мәнді сақтайды немесе қандай әрекетті бастайды?"
    return {"answer": answer, "mode": "demo", "disclaimer": "Демонстрациялық жауап"}

