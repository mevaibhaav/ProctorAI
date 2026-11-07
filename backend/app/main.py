import csv, io, os
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from datetime import datetime, timedelta, timezone
from typing import Literal
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile, Response, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload
from .database import Base, engine, get_db
from .models import User, Exam, Question, Attempt, AttemptPresence, ProctoringEvent, ProctoringEvidence, ExamResult, Notification, AdminSetting, StudentActivity
from .security import hash_password, verify_password, token_for, current_user, require_admin
from .scoring import score_events

app = FastAPI(title="ProctorAI", version="1.0.0", description="Privacy-first local exam and human-reviewed proctoring platform")
WARNING_LIMIT = 5
WINDOW_SWITCH_LIMIT = 2
ACTIVE_SESSION_GRACE_SECONDS = 30

def should_pause_attempt(warning_count: int, window_switch_count: int) -> bool:
    return warning_count >= WARNING_LIMIT or window_switch_count > WINDOW_SWITCH_LIMIT
origins = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
_analyzer = None

class Register(BaseModel): name: str = Field(min_length=2, max_length=120); email: EmailStr; password: str = Field(min_length=10)
class Login(BaseModel): email: EmailStr; password: str
class QuestionIn(BaseModel): prompt: str; kind: Literal["choice","short"] = "choice"; options: list[str] = []; correct_answer: str = ""; points: float = Field(default=1, gt=0)
class ExamIn(BaseModel): title: str; description: str = ""; duration_minutes: int = Field(default=60, gt=0, le=600); published: bool = False; questions: list[QuestionIn] = []
class AnswerIn(BaseModel): question_id: int; answer: str = ""
class StartIn(BaseModel): exam_id: int; consent: bool
class EventIn(BaseModel): attempt_id: int; event_type: Literal["looking_away","face_absent","multiple_faces","camera_lost","head_deviation","window_switch","screenshot_attempt"]; duration_seconds: float = Field(default=1, ge=0, le=3600); details: dict = {}
class ReviewIn(BaseModel): review_status: Literal["reviewed","no_issue","investigate"]; review_note: str = ""

def user_json(u): return {"id":u.id,"name":u.name,"email":u.email,"role":u.role,"student_id":u.student_id}
def utc_datetime(value):
    """SQLite drops timezone metadata; all stored application times are UTC."""
    return value.replace(tzinfo=timezone.utc) if value and value.tzinfo is None else value
def attempt_times(attempt, exam):
    started=utc_datetime(attempt.started_at)
    return {"started_at":started.isoformat(),"expires_at":(started+timedelta(minutes=exam.duration_minutes)).isoformat()}
def exam_json(e, include_answers=False):
    return {"id":e.id,"title":e.title,"description":e.description,"duration_minutes":e.duration_minutes,"published":e.published,"questions":[{"id":q.id,"prompt":q.prompt,"kind":q.kind,"options":q.options,"points":q.points,**({"correct_answer":q.correct_answer} if include_answers else {})} for q in sorted(e.questions,key=lambda x:x.position)]}
def get_attempt(db, aid, user):
    a=db.get(Attempt, aid)
    if not a: raise HTTPException(404,"Attempt not found")
    if user.role != "admin" and a.user_id != user.id: raise HTTPException(403,"This attempt belongs to another student")
    return a

def log_student_activity(db, attempt, activity_type, details=None):
    """Record exam workflow metadata without recording answer text or video."""
    db.add(StudentActivity(
        user_id=attempt.user_id,
        attempt_id=attempt.id,
        exam_id=attempt.exam_id,
        activity_type=activity_type,
        details=details or {},
    ))

def touch_attempt_presence(db, attempt_id):
    now=datetime.now(timezone.utc)
    presence=db.get(AttemptPresence,attempt_id)
    if presence is None:
        presence=AttemptPresence(attempt_id=attempt_id,last_seen_at=now)
        db.add(presence)
        return True
    last_seen=utc_datetime(presence.last_seen_at)
    if last_seen and last_seen >= now-timedelta(seconds=8):
        return False
    presence.last_seen_at=now
    return True

@app.on_event("startup")
def startup():
    Base.metadata.create_all(engine)
    if os.getenv("SEED_DEMO", "true").lower() != "true": return
    from .database import SessionLocal
    db=SessionLocal()
    try:
        if not db.scalar(select(User).where(User.email=="admin@proctorai.example.com")):
            db.add_all([User(name="Demo Administrator",email="admin@proctorai.example.com",password_hash=hash_password("AdminDemo2026!"),role="admin"),User(name="Aarav Sharma",email="student@proctorai.example.com",password_hash=hash_password("StudentDemo2026!"),role="student",student_id="STU-2048")]); db.commit()
        if not db.scalar(select(Exam)):
            e=Exam(title="Foundations of Computer Science",description="A 30-minute sample assessment covering algorithms and data structures.",duration_minutes=30,published=True)
            e.questions=[Question(prompt="What is the time complexity of binary search on a sorted array?",kind="choice",options=["O(n)","O(log n)","O(n log n)","O(1)"],correct_answer="O(log n)",points=2,position=0),Question(prompt="Which data structure follows FIFO order?",kind="choice",options=["Stack","Queue","Tree","Heap"],correct_answer="Queue",points=2,position=1),Question(prompt="Describe one benefit of using a hash table.",kind="short",correct_answer="",points=3,position=2)]
            db.add(e); db.commit()
        if not db.scalar(select(Exam).where(Exam.title=="Python Test")):
            questions=[
                ("Which keyword displays text in Python?",["show","print","write","echo"],"print"),
                ("Which symbol starts a single-line comment?",["//","<!--","#","**"],"#"),
                ("Which type stores an ordered, changeable collection?",["list","tuple","set","bool"],"list"),
                ("What does len([3, 4, 5]) return?",["2","3","4","5"],"3"),
                ("Which value represents no value in Python?",["null","undefined","None","void"],"None"),
                ("Which keyword defines a function?",["function","def","fun","make"],"def"),
                ("What is the result of 7 // 2?",["3","3.5","4","2"],"3"),
                ("Which brackets create a dictionary?",["[]","()","{}","<>"],"{}"),
                ("Which values are generated by a loop over range(3)?",["0, 1, 2","1, 2, 3","0, 1, 2, 3","3"],"0, 1, 2"),
                ("Which keyword starts a conditional branch?",["when","if","case","check"],"if"),
            ]
            exam=Exam(title="Python Test",description="Ten beginner-friendly Python questions. Choose one answer for each question.",duration_minutes=30,published=True)
            exam.questions=[Question(prompt=prompt,kind="choice",options=options,correct_answer=answer,points=1,position=i) for i,(prompt,options,answer) in enumerate(questions)]
            db.add(exam); db.commit()
        if not db.scalar(select(Exam).where(Exam.title=="Machine Learning Basics")):
            questions=[
                ("What is machine learning?",["A way for computers to learn patterns from data","A type of computer hardware","A programming language","A method for storing files"],"A way for computers to learn patterns from data"),
                ("What kind of data is used in supervised learning?",["Unlabeled data only","Labeled examples with known answers","No data","Randomly generated passwords"],"Labeled examples with known answers"),
                ("What is the purpose of training data?",["To teach a model patterns to use for predictions","To decorate charts","To connect a computer to Wi-Fi","To replace the operating system"],"To teach a model patterns to use for predictions"),
                ("Which task predicts a category such as cat or dog?",["Regression","Classification","Sorting","Compression"],"Classification"),
                ("Which task predicts a number such as tomorrow's temperature?",["Classification","Regression","Encryption","Clustering"],"Regression"),
            ]
            exam=Exam(title="Machine Learning Basics",description="A short beginner quiz about machine learning concepts. Five multiple-choice questions, 2 marks each.",duration_minutes=15,published=True)
            exam.questions=[Question(prompt=prompt,kind="choice",options=options,correct_answer=answer,points=2,position=i) for i,(prompt,options,answer) in enumerate(questions)]
            db.add(exam); db.commit()
    finally: db.close()

@app.get("/api/health")
def health(): return {"status":"ok","service":"ProctorAI","vision":"local transient frame analysis; frames are not persisted"}

@app.post("/api/proctoring/analyze-frame")
async def analyze_frame(frame: UploadFile=File(...), db: Session=Depends(get_db), user: User=Depends(current_user)):
    """Process a single transient webcam frame on this machine; never writes it to disk."""
    global _analyzer
    active_attempt=db.scalar(select(Attempt).where(Attempt.user_id==user.id,Attempt.status=="in_progress").order_by(Attempt.started_at.desc()))
    if active_attempt and touch_attempt_presence(db,active_attempt.id):
        db.commit()
    if frame.content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(415, "Upload a JPEG, PNG, or WebP frame")
    payload=await frame.read(2_000_001)
    if len(payload)>2_000_000: raise HTTPException(413,"Frame exceeds 2 MB")
    try:
        import cv2, numpy as np
        image=cv2.imdecode(np.frombuffer(payload,dtype=np.uint8),cv2.IMREAD_COLOR)
        if image is None: raise ValueError("Invalid image")
        if _analyzer is None:
            from .vision import LocalFaceAnalyzer
            _analyzer=LocalFaceAnalyzer()
        result=_analyzer.analyze(image)
        return {"face_count":result.face_count,"gaze":result.gaze,"yaw":result.yaw,"pitch":result.pitch,"processed_locally":True,"stored":False}
    except RuntimeError as exc:
        raise HTTPException(503,str(exc))
    except Exception as exc:
        raise HTTPException(422,"Frame could not be analysed") from exc

@app.post("/api/auth/register")
def register(data: Register, db: Session=Depends(get_db)):
    email=data.email.lower()
    if db.scalar(select(User).where(User.email==email)): raise HTTPException(409,"Email already registered")
    u=User(name=data.name,email=email,password_hash=hash_password(data.password),role="student",student_id=f"STU-{datetime.now().strftime('%y%m%d%H%M%S')}")
    db.add(u); db.commit(); db.refresh(u)
    return {"access_token":token_for(u),"token_type":"bearer","user":user_json(u)}

@app.post("/api/auth/login")
def login(data: Login, db: Session=Depends(get_db)):
    u=db.scalar(select(User).where(User.email==data.email.lower()))
    if not u or not verify_password(data.password,u.password_hash): raise HTTPException(401,"Email or password is incorrect")
    return {"access_token":token_for(u),"token_type":"bearer","user":user_json(u)}

@app.get("/api/auth/me")
def me(user: User=Depends(current_user)): return user_json(user)

@app.get("/api/student/dashboard")
def student_dashboard(db: Session=Depends(get_db), user: User=Depends(current_user)):
    attempts=db.scalars(select(Attempt).where(Attempt.user_id==user.id).order_by(Attempt.started_at.desc())).all()
    # Spell out both join conditions: implicit joins are ambiguous here because
    # ExamResult, Attempt, and Exam are all connected through multiple paths.
    recent=db.execute(
        select(ExamResult, Attempt, Exam)
        .join(Attempt, ExamResult.attempt_id == Attempt.id)
        .join(Exam, Attempt.exam_id == Exam.id)
        .where(Attempt.user_id == user.id)
        .order_by(ExamResult.created_at.desc())
        .limit(5)
    ).all()
    return {"user":user_json(user),"available_exams":[exam_json(e) for e in db.scalars(select(Exam).where(Exam.published==True)).all()],"attempts":[{"id":a.id,"exam_id":a.exam_id,"status":a.status,"started_at":a.started_at,"score":a.result.score if a.result else None,"max_score":a.result.max_score if a.result else None} for a in attempts],"recent_results":[{"id":r.id,"exam_title":e.title,"score":r.score,"max_score":r.max_score,"manual_review_required":r.manual_review_required,"submitted_at":a.submitted_at} for r,a,e in recent],"notifications":[{"id":n.id,"message":n.message,"created_at":n.created_at} for n in db.scalars(select(Notification).where(Notification.user_id==user.id).order_by(Notification.created_at.desc()).limit(5)).all()]}

@app.get("/api/student/profile")
def student_profile(user: User=Depends(current_user)): return user_json(user)

@app.get("/api/student/exams")
def student_exams(db: Session=Depends(get_db), user: User=Depends(current_user)):
    return [exam_json(e) for e in db.scalars(select(Exam).where(Exam.published==True)).all()]

@app.get("/api/student/results")
def student_results(db: Session=Depends(get_db), user: User=Depends(current_user)):
    rows=db.execute(
        select(ExamResult, Attempt, Exam)
        .join(Attempt, ExamResult.attempt_id == Attempt.id)
        .join(Exam, Attempt.exam_id == Exam.id)
        .where(Attempt.user_id == user.id)
    ).all()
    return [{"id":r.id,"exam_title":e.title,"score":r.score,"max_score":r.max_score,"manual_review_required":r.manual_review_required,"submitted_at":a.submitted_at} for r,a,e in rows]

@app.post("/api/attempts/start")
def start_attempt(data: StartIn, db: Session=Depends(get_db), user: User=Depends(current_user)):
    if not data.consent: raise HTTPException(400,"Explicit camera and local analysis consent is required")
    exam=db.scalar(select(Exam).options(selectinload(Exam.questions)).where(Exam.id==data.exam_id,Exam.published==True))
    if not exam: raise HTTPException(404,"Published exam not found")
    existing=db.scalar(select(Attempt).where(Attempt.user_id==user.id,Attempt.exam_id==exam.id,Attempt.status=="in_progress"))
    if existing:
        touch_attempt_presence(db,existing.id); db.commit()
        return {"id":existing.id,"attempt_id":existing.id,"exam":exam_json(exam),"answers":existing.answers,**attempt_times(existing,exam)}
    a=Attempt(user_id=user.id,exam_id=exam.id,consent_at=datetime.now(timezone.utc),answers=[]); db.add(a); db.flush()
    touch_attempt_presence(db,a.id)
    log_student_activity(db,a,"attempt_started")
    db.commit(); db.refresh(a)
    return {"id":a.id,"attempt_id":a.id,"exam":exam_json(exam),"answers":a.answers,**attempt_times(a,exam)}

@app.get("/api/attempts/{aid}")
def attempt_detail(aid:int, db:Session=Depends(get_db), user:User=Depends(current_user)):
    a=get_attempt(db,aid,user); e=db.scalar(select(Exam).options(selectinload(Exam.questions)).where(Exam.id==a.exam_id))
    return {"id":a.id,"exam":exam_json(e),"answers":a.answers,"status":a.status,**attempt_times(a,e),"risk_score":a.risk_score}

@app.post("/api/attempts/{aid}/heartbeat")
def attempt_heartbeat(aid:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    a=get_attempt(db,aid,user)
    if a.status!="in_progress": raise HTTPException(409,"Attempt is no longer active")
    touch_attempt_presence(db,a.id); db.commit()
    return {"active":True,"last_seen_at":datetime.now(timezone.utc)}

@app.post("/api/attempts/{aid}/answer")
def save_answer(aid:int,data:AnswerIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    a=get_attempt(db,aid,user)
    if a.status!="in_progress": raise HTTPException(409,"Attempt is already submitted")
    exam=db.get(Exam,a.exam_id)
    started=a.started_at if a.started_at.tzinfo else a.started_at.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc)>=started+timedelta(minutes=exam.duration_minutes): raise HTTPException(409,"The exam time has expired; submit the attempt")
    q=db.get(Question,data.question_id)
    if not q or q.exam_id!=a.exam_id: raise HTTPException(404,"Question not found for this exam")
    answers={x["question_id"]:x["answer"] for x in a.answers}; answers[q.id]=data.answer; a.answers=[{"question_id":k,"answer":v} for k,v in answers.items()]
    log_student_activity(db,a,"answer_saved",{"question_id":q.id,"answered":bool(data.answer.strip())})
    db.commit()
    return {"saved":True,"question_id":q.id}

@app.post("/api/attempts/{aid}/submit")
def submit(aid:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    a=get_attempt(db,aid,user)
    if a.status=="submitted": return {"status":"submitted","result_id":a.result.id if a.result else None}
    if a.status!="in_progress": raise HTTPException(409,"This attempt is paused for administrator review")
    e=db.scalar(select(Exam).options(selectinload(Exam.questions)).where(Exam.id==a.exam_id)); answers={x["question_id"]:x["answer"].strip() for x in a.answers}
    score=0; maximum=0; manual=False
    for q in e.questions:
        maximum += q.points
        if q.kind=="choice" and answers.get(q.id,"").casefold()==q.correct_answer.casefold(): score += q.points
        elif q.kind!="choice" and answers.get(q.id): manual=True
    a.status="submitted"; a.submitted_at=datetime.now(timezone.utc); r=ExamResult(attempt=a,score=score,max_score=maximum,manual_review_required=manual); db.add(r)
    log_student_activity(db,a,"exam_submitted",{"score":score,"max_score":maximum,"manual_review_required":manual})
    db.commit(); db.refresh(r)
    return {"status":"submitted","result_id":r.id,"score":score,"max_score":maximum,"manual_review_required":manual,"risk_score":a.risk_score}

@app.post("/api/proctoring/events")
def create_event(data:EventIn,db:Session=Depends(get_db),user:User=Depends(current_user)):
    a=get_attempt(db,data.attempt_id,user)
    if a.status!="in_progress": raise HTTPException(409,"Cannot add events to a submitted attempt")
    events=db.scalars(select(ProctoringEvent).where(ProctoringEvent.attempt_id==a.id)).all()
    warning_count=sum(1 for event in events if event.details.get("student_warning"))
    switch_count=sum(1 for event in events if event.event_type=="window_switch")+(1 if data.event_type=="window_switch" else 0)
    details={**data.details,"student_warning":True,"warning_number":warning_count+1}
    ev=ProctoringEvent(attempt_id=a.id,event_type=data.event_type,duration_seconds=data.duration_seconds,details=details,severity="high" if data.event_type in ("multiple_faces","screenshot_attempt") else "medium" if data.event_type=="window_switch" else "low")
    db.add(ev); db.flush(); events.append(ev)
    a.risk_score=score_events([{"event_type":x.event_type,"duration_seconds":x.duration_seconds} for x in events])["score"]
    warning_count += 1
    switch_limit_exceeded=data.event_type=="window_switch" and switch_count>WINDOW_SWITCH_LIMIT
    terminated=should_pause_attempt(warning_count,switch_count)
    if terminated:
        a.status="needs_review"
        a.submitted_at=datetime.now(timezone.utc)
    log_student_activity(db,a,"proctoring_event",{"event_type":data.event_type,"warning_number":warning_count,"risk_score":a.risk_score})
    if terminated:
        log_student_activity(db,a,"attempt_paused",{"reason":"window_switch_limit" if switch_limit_exceeded else "warning_limit"})
    db.commit()
    return {"id":ev.id,"risk_score":a.risk_score,"event_count":len(events),"warning_count":warning_count,"warning_limit":WARNING_LIMIT,"window_switch_count":switch_count,"window_switch_limit":WINDOW_SWITCH_LIMIT,"terminated":terminated,"termination_reason":"window_switch_limit" if switch_limit_exceeded else "warning_limit" if warning_count>=WARNING_LIMIT else None}

@app.get("/api/proctoring/events/{aid}")
def get_events(aid:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    get_attempt(db,aid,user); return [{"id":e.id,"event_type":e.event_type,"severity":e.severity,"duration_seconds":e.duration_seconds,"occurred_at":e.occurred_at,"details":e.details,"review_status":e.review_status,"review_note":e.review_note} for e in db.scalars(select(ProctoringEvent).where(ProctoringEvent.attempt_id==aid).order_by(ProctoringEvent.occurred_at.desc())).all()]

@app.get("/api/proctoring/score/{aid}")
def get_score(aid:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    get_attempt(db,aid,user); events=db.scalars(select(ProctoringEvent).where(ProctoringEvent.attempt_id==aid)).all(); return score_events([{"event_type":e.event_type,"duration_seconds":e.duration_seconds} for e in events])

@app.get("/api/admin/dashboard")
def admin_dashboard(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    recent=db.execute(
        select(ExamResult,Attempt,User,Exam)
        .join(Attempt,ExamResult.attempt_id==Attempt.id)
        .join(User,Attempt.user_id==User.id)
        .join(Exam,Attempt.exam_id==Exam.id)
        .order_by(ExamResult.created_at.desc()).limit(5)
    ).all()
    active_cutoff=datetime.now(timezone.utc)-timedelta(seconds=ACTIVE_SESSION_GRACE_SECONDS)
    active_count=db.scalar(select(func.count()).select_from(Attempt).join(AttemptPresence,AttemptPresence.attempt_id==Attempt.id).where(Attempt.status=="in_progress",AttemptPresence.last_seen_at>=active_cutoff)) or 0
    return {"students":db.scalar(select(func.count()).select_from(User).where(User.role=="student")),"exams":db.scalar(select(func.count()).select_from(Exam)),"active_attempts":active_count,"completed_attempts":db.scalar(select(func.count()).select_from(Attempt).where(Attempt.status=="submitted")),"event_count":db.scalar(select(func.count()).select_from(ProctoringEvent)),"high_risk":db.scalar(select(func.count()).select_from(Attempt).where(Attempt.risk_score>=75)),"risk_distribution":[{"range":label,"count":db.scalar(select(func.count()).select_from(Attempt).where(Attempt.risk_score>=lo,Attempt.risk_score<hi))} for label,lo,hi in [("Normal",0,30),("Low",30,50),("Moderate",50,75),("High",75,101)]],"recent_results":[{"id":r.id,"student":s.name,"student_id":s.student_id,"exam":e.title,"score":r.score,"max_score":r.max_score,"manual_review_required":r.manual_review_required,"submitted_at":a.submitted_at} for r,a,s,e in recent]}

@app.get("/api/admin/students")
def admin_students(q:str="",db:Session=Depends(get_db),user:User=Depends(require_admin)):
    stmt=select(User).where(User.role=="student")
    if q: stmt=stmt.where(User.name.ilike(f"%{q}%")|User.email.ilike(f"%{q}%"))
    return [user_json(u) for u in db.scalars(stmt.order_by(User.name)).all()]

@app.get("/api/admin/activity")
def admin_activity(limit:int=Query(default=250,ge=1,le=1000),db:Session=Depends(get_db),user:User=Depends(require_admin)):
    """Recent exam workflow activity across all students; never includes answer text or video."""
    stmt=(select(StudentActivity,User,Exam)
        .join(User,StudentActivity.user_id==User.id)
        .join(Exam,StudentActivity.exam_id==Exam.id)
        .order_by(StudentActivity.occurred_at.desc())
        .limit(limit))
    return [{"id":activity.id,"attempt_id":activity.attempt_id,"student":student.name,
        "student_id":student.student_id,"exam":exam.title,"activity_type":activity.activity_type,
        "details":activity.details,"occurred_at":activity.occurred_at}
        for activity,student,exam in db.execute(stmt).all()]

@app.get("/api/admin/exams")
def admin_exams(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    return [exam_json(e,True) for e in db.scalars(select(Exam).options(selectinload(Exam.questions)).order_by(Exam.id.desc())).all()]

@app.post("/api/exams")
def create_exam(data:ExamIn,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    if data.published and not data.questions: raise HTTPException(422,"Add at least one question before publishing an exam")
    e=Exam(title=data.title,description=data.description,duration_minutes=data.duration_minutes,published=data.published,questions=[Question(**q.model_dump(),position=i) for i,q in enumerate(data.questions)]); db.add(e); db.commit(); db.refresh(e); return exam_json(e,True)

@app.put("/api/exams/{eid}")
def update_exam(eid:int,data:ExamIn,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    e=db.scalar(select(Exam).options(selectinload(Exam.questions)).where(Exam.id==eid))
    if not e: raise HTTPException(404,"Exam not found")
    if data.published and not data.questions: raise HTTPException(422,"Add at least one question before publishing an exam")
    e.title=data.title;e.description=data.description;e.duration_minutes=data.duration_minutes;e.published=data.published;e.questions=[Question(**q.model_dump(),position=i) for i,q in enumerate(data.questions)];db.commit();return exam_json(e,True)

@app.delete("/api/exams/{eid}")
def delete_exam(eid:int,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    e=db.get(Exam,eid)
    if not e: raise HTTPException(404,"Exam not found")
    if db.scalar(select(Attempt).where(Attempt.exam_id==eid)): raise HTTPException(409,"This exam has student attempts and cannot be deleted. Unpublish it instead.")
    db.delete(e);db.commit();return {"deleted":True}

@app.get("/api/admin/events")
def admin_events(status:str|None=None,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    stmt=(select(ProctoringEvent,Attempt,User,Exam)
        .join(Attempt,ProctoringEvent.attempt_id==Attempt.id)
        .join(User,Attempt.user_id==User.id)
        .join(Exam,Attempt.exam_id==Exam.id)
        .order_by(ProctoringEvent.occurred_at.desc()))
    if status: stmt=stmt.where(ProctoringEvent.review_status==status)
    rows=db.execute(stmt).all()
    event_ids=[event.id for event,_,_,_ in rows]
    evidence_ids=set(db.scalars(select(ProctoringEvidence.event_id).where(ProctoringEvidence.event_id.in_(event_ids))).all()) if event_ids else set()
    return [{"id":ev.id,"attempt_id":a.id,"student":s.name,"student_id":s.student_id,"exam":e.title,"event_type":ev.event_type,"severity":ev.severity,"duration_seconds":ev.duration_seconds,"occurred_at":ev.occurred_at,"review_status":ev.review_status,"review_note":ev.review_note,"risk_score":a.risk_score,"details":ev.details,"snapshot_available":ev.id in evidence_ids} for ev,a,s,e in rows]

@app.post("/api/proctoring/events/{event_id}/snapshot",status_code=201)
async def upload_event_snapshot(event_id:int,photo:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(current_user)):
    ev=db.get(ProctoringEvent,event_id)
    if not ev: raise HTTPException(404,"Proctoring event not found")
    attempt=get_attempt(db,ev.attempt_id,user)
    if user.role!="student" or attempt.user_id!=user.id: raise HTTPException(403,"Only the student who owns this event may attach its camera snapshot")
    if photo.content_type not in ("image/jpeg","image/png"): raise HTTPException(415,"Snapshot must be a JPEG or PNG image")
    if db.scalar(select(ProctoringEvidence).where(ProctoringEvidence.event_id==ev.id)):
        raise HTTPException(409,"A snapshot is already attached to this event")
    payload=await photo.read(2_000_001)
    if len(payload)>2_000_000: raise HTTPException(413,"Snapshot exceeds 2 MB")
    try:
        import cv2, numpy as np
        frame=cv2.imdecode(np.frombuffer(payload,dtype=np.uint8),cv2.IMREAD_COLOR)
        if frame is None: raise ValueError("Invalid image")
        ok,encoded=cv2.imencode(".jpg",frame,[int(cv2.IMWRITE_JPEG_QUALITY),82])
        if not ok: raise ValueError("Image encoding failed")
        payload=encoded.tobytes()
    except Exception as exc:
        raise HTTPException(422,"Snapshot image could not be decoded") from exc
    evidence_dir=Path(__file__).resolve().parents[1]/"evidence"
    evidence_dir.mkdir(parents=True,exist_ok=True)
    image_path=evidence_dir/f"event-{ev.id}-{__import__('uuid').uuid4().hex}.jpg"
    image_path.write_bytes(payload)
    try:
        db.add(ProctoringEvidence(event_id=ev.id,storage_path=str(image_path),media_type="image/jpeg",size_bytes=len(payload)))
        db.commit()
    except Exception:
        db.rollback(); image_path.unlink(missing_ok=True); raise
    return {"event_id":ev.id,"snapshot_available":True,"stored_locally":True}

@app.get("/api/admin/events/{event_id}/snapshot")
def view_event_snapshot(event_id:int,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    evidence=db.scalar(select(ProctoringEvidence).where(ProctoringEvidence.event_id==event_id))
    if not evidence: raise HTTPException(404,"No snapshot is stored for this event")
    path=Path(evidence.storage_path).resolve()
    evidence_root=(Path(__file__).resolve().parents[1]/"evidence").resolve()
    if not path.is_relative_to(evidence_root) or not path.is_file(): raise HTTPException(404,"Stored snapshot file is unavailable")
    return FileResponse(path,media_type=evidence.media_type,headers={"Cache-Control":"no-store"})

@app.patch("/api/admin/events/{event_id}")
def review_event(event_id:int,data:ReviewIn,db:Session=Depends(get_db),user:User=Depends(require_admin)):
    ev=db.get(ProctoringEvent,event_id)
    if not ev: raise HTTPException(404,"Event not found")
    ev.review_status=data.review_status;ev.review_note=data.review_note;db.commit();return {"id":ev.id,"review_status":ev.review_status}

@app.get("/api/admin/live-sessions")
def live_sessions(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    cutoff=datetime.now(timezone.utc)-timedelta(seconds=ACTIVE_SESSION_GRACE_SECONDS)
    stmt=(select(Attempt,User,Exam,AttemptPresence)
        .join(AttemptPresence,AttemptPresence.attempt_id==Attempt.id)
        .join(User,Attempt.user_id==User.id)
        .join(Exam,Attempt.exam_id==Exam.id)
        .where(Attempt.status=="in_progress",AttemptPresence.last_seen_at>=cutoff)
        .order_by(AttemptPresence.last_seen_at.desc()))
    rows=db.execute(stmt).all()
    return [{"attempt_id":a.id,"student":s.name,"student_id":s.student_id,"exam":e.title,"started_at":a.started_at,"last_seen_at":presence.last_seen_at,"risk_score":a.risk_score,"event_count":db.scalar(select(func.count()).select_from(ProctoringEvent).where(ProctoringEvent.attempt_id==a.id))} for a,s,e,presence in rows]

@app.get("/api/admin/results")
def admin_results(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    rows=db.execute(
        select(ExamResult,Attempt,User,Exam)
        .join(Attempt,ExamResult.attempt_id==Attempt.id)
        .join(User,Attempt.user_id==User.id)
        .join(Exam,Attempt.exam_id==Exam.id)
        .order_by(ExamResult.created_at.desc())
    ).all()
    return [{"id":r.id,"student":u.name,"student_id":u.student_id,"exam":e.title,"score":r.score,"max_score":r.max_score,"manual_review_required":r.manual_review_required,"submitted_at":a.submitted_at,"risk_score":a.risk_score} for r,a,u,e in rows]

@app.get("/api/admin/analytics")
def admin_analytics(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    exams=db.scalars(select(Exam)).all()
    return [{"exam":e.title,"attempts":db.scalar(select(func.count()).select_from(Attempt).where(Attempt.exam_id==e.id)),"avg_score":db.scalar(select(func.avg(ExamResult.score)).join(Attempt).where(Attempt.exam_id==e.id)) or 0,"events":db.scalar(select(func.count()).select_from(ProctoringEvent).join(Attempt).where(Attempt.exam_id==e.id))} for e in exams]

@app.get("/api/admin/reports/results.csv")
def export_results(db:Session=Depends(get_db),user:User=Depends(require_admin)):
    rows=db.execute(select(ExamResult,Attempt,User,Exam).join(Attempt,ExamResult.attempt_id==Attempt.id).join(User,Attempt.user_id==User.id).join(Exam,Attempt.exam_id==Exam.id)).all(); out=io.StringIO(); w=csv.writer(out);w.writerow(["student_id","student","exam","score","max_score","risk_score","submitted_at"])
    for r,a,u,e in rows:w.writerow([u.student_id,u.name,e.title,r.score,r.max_score,a.risk_score,a.submitted_at])
    return Response(out.getvalue(),media_type="text/csv",headers={"Content-Disposition":"attachment; filename=proctorai-results.csv"})
