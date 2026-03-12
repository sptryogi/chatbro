from fastapi import FastAPI, File, UploadFile, HTTPException, Depends, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional, Literal
import os
import json
import bcrypt
from datetime import datetime
from supabase import create_client, Client
from google import genai
from google.genai import types
import openai
from openai import OpenAI
import httpx

app = FastAPI(title="ChatBro API")

# CORS
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Ganti bagian CORS ini:
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://chatbro-web.vercel.app",  # ✅ Hapus spasi!
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
KIMI_API_KEY = os.getenv("KIMI_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Models
class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    model: Literal["gemini", "deepseek", "groq", "kimi"]
    messages: List[dict]
    temperature: float = 0.7
    top_p: float = 0.9
    max_tokens: int = 2048
    system_instruction: Optional[str] = None
    knowledge_context: Optional[str] = None

class SessionCreate(BaseModel):
    title: str
    model: str
    settings: dict
    system_instruction: Optional[str] = None

security = HTTPBearer()

# Auth
async def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)):
    token = credentials.credentials
    try:
        # Simplified auth - in production use JWT properly
        user = supabase.table("users").select("*").eq("username", token).single().execute()
        if not user.data:
            raise HTTPException(status_code=401, detail="Invalid token")
        return user.data
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))

# Routes
@app.post("/auth/login")
async def login(req: LoginRequest):
    user = supabase.table("users").select("*").eq("username", req.username).single().execute()
    if not user.data:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # if not bcrypt.checkpw(req.password.encode(), user.data["password_hash"].encode()):
    #     raise HTTPException(status_code=401, detail="Invalid credentials")
    if req.password != user.data["password_hash"]:  # Plain text compare
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    return {"token": req.username, "user": {"id": user.data["id"], "username": user.data["username"]}}

@app.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(verify_token)):
    logger.info(f"Chat request: model={req.model}, user={user['username']}")
    
    try:
        # Cek API keys tersedia
        api_keys = {
            "gemini": GEMINI_API_KEY,
            "deepseek": DEEPSEEK_API_KEY,
            "groq": GROQ_API_KEY,
            "kimi": KIMI_API_KEY
        }
        
        if not api_keys.get(req.model):
            logger.error(f"API key for {req.model} not configured")
            raise HTTPException(status_code=500, detail=f"API key for {req.model} not configured")
        
        # Build messages
        system_content = req.system_instruction or "You are a helpful assistant."
        if req.knowledge_context:
            system_content += f"\n\nContext:\n{req.knowledge_context}"
        
        messages = [{"role": "system", "content": system_content}] + req.messages
        logger.info(f"Sending {len(messages)} messages to {req.model}")
        
        # Route ke model yang sesuai
        if req.model == "gemini":
            result = await chat_gemini(req, messages)
        elif req.model == "deepseek":
            result = await chat_deepseek(req, messages)
        elif req.model == "groq":
            result = await chat_groq(req, messages)
        elif req.model == "kimi":
            result = await chat_kimi(req, messages)
        else:
            raise HTTPException(status_code=400, detail="Invalid model")
            
        logger.info(f"Chat success: {req.model}")
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error ({req.model}): {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

async def chat_gemini(req: ChatRequest, messages: List[dict]):
    try:
        # Buat client baru
        client = genai.Client(api_key=GEMINI_API_KEY)
        
        # Convert messages ke format Gemini
        contents = []
        system_instruction = None
        
        for msg in messages:
            if msg["role"] == "system":
                system_instruction = msg["content"]
            elif msg["role"] == "user":
                contents.append({"role": "user", "parts": [{"text": msg["content"]}]})
            elif msg["role"] == "assistant":
                contents.append({"role": "model", "parts": [{"text": msg["content"]}]})
        
        # Generate response
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=contents,
            config=types.GenerateContentConfig(
                temperature=req.temperature,
                top_p=req.top_p,
                max_output_tokens=req.max_tokens,
                system_instruction=system_instruction
            )
        )
        
        return {"response": response.text, "model": "gemini"}
    except Exception as e:
        logger.error(f"Gemini error: {str(e)}")
        raise

# Update fungsi chat_deepseek - fix URL:
async def chat_deepseek(req: ChatRequest, messages: List[dict]):
    try:
        client = openai.OpenAI(
            api_key=DEEPSEEK_API_KEY, 
            base_url="https://api.deepseek.com"  # ✅ Hapus spasi!
        )
        
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens
        )
        return {"response": response.choices[0].message.content, "model": "deepseek"}
    except Exception as e:
        logger.error(f"Deepseek error: {str(e)}")
        raise

# Update fungsi chat_groq - fix URL:
async def chat_groq(req: ChatRequest, messages: List[dict]):
    try:
        client = openai.OpenAI(
            api_key=GROQ_API_KEY, 
            base_url="https://api.groq.com/openai/v1"  # ✅ Hapus spasi!
        )
        
        response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens
        )
        return {"response": response.choices[0].message.content, "model": "groq"}
    except Exception as e:
        logger.error(f"Groq error: {str(e)}")
        raise

# Update fungsi chat_kimi - fix URL:
async def chat_kimi(req: ChatRequest, messages: List[dict]):
    try:
        client = OpenAI(
            api_key=KIMI_API_KEY, 
            base_url="https://api.moonshot.ai/v1"  # ✅ Hapus spasi!
        )
        
        response = client.chat.completions.create(
            model="kimi-k2-0905-preview",
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens
        )
        return {"response": response.choices[0].message.content, "model": "kimi"}
    except Exception as e:
        logger.error(f"Kimi error: {str(e)}")
        raise

# Sessions
@app.post("/sessions")
async def create_session(req: SessionCreate, user: dict = Depends(verify_token)):
    try:
        # Kalau title kosong, akan diupdate nanti
        session = supabase.table("chat_sessions").insert({
            "user_id": user["id"],
            "title": req.title or "New Chat",
            "model": req.model,
            "settings": req.settings,
            "system_instruction": req.system_instruction
        }).execute()
        return session.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/sessions")
async def get_sessions(user: dict = Depends(verify_token)):
    sessions = supabase.table("chat_sessions").select("*").eq("user_id", user["id"]).order("updated_at", desc=True).execute()
    return sessions.data

@app.get("/sessions/{session_id}/messages")
async def get_messages(session_id: str, user: dict = Depends(verify_token)):
    messages = supabase.table("chat_messages").select("*").eq("session_id", session_id).order("created_at").execute()
    return messages.data

class MessageCreate(BaseModel):
    role: str
    content: str

@app.post("/sessions/{session_id}/messages")
async def add_message(session_id: str, req: MessageCreate, user: dict = Depends(verify_token)):
    message = supabase.table("chat_messages").insert({
        "session_id": session_id,
        "role": req.role,
        "content": req.content
    }).execute()
    return message.data[0]

# Knowledge Management
@app.post("/knowledge/upload")
async def upload_knowledge(
    file: UploadFile = File(...),
    user: dict = Depends(verify_token)
):
    try:
        # Read file content
        content = await file.read()
        file_ext = file.filename.split(".")[-1].lower()
        
        # Extract text based on file type
        extracted_text = ""
        if file_ext == "txt":
            extracted_text = content.decode("utf-8")
        elif file_ext == "pdf":
            import io
            from PyPDF2 import PdfReader
            pdf = PdfReader(io.BytesIO(content))
            for page in pdf.pages:
                extracted_text += page.extract_text() + "\n"
        elif file_ext == "docx":
            import io
            from docx import Document
            doc = Document(io.BytesIO(content))
            for para in doc.paragraphs:
                extracted_text += para.text + "\n"
        
        # Upload to Supabase Storage
        file_path = f"{user['id']}/{datetime.now().isoformat()}_{file.filename}"
        supabase.storage.from_("knowledge-files").upload(file_path, content)
        
        # Save metadata to database
        knowledge = supabase.table("knowledge_files").insert({
            "user_id": user["id"],
            "filename": file_path,
            "original_name": file.filename,
            "file_type": file_ext,
            "file_size": len(content),
            "storage_path": file_path,
            "extracted_text": extracted_text[:10000]  # Limit stored text
        }).execute()
        
        return {"success": True, "file": knowledge.data[0]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge")
async def get_knowledge(user: dict = Depends(verify_token)):
    files = supabase.table("knowledge_files").select("*").eq("user_id", user["id"]).execute()
    return files.data

@app.delete("/knowledge/{file_id}")
async def delete_knowledge(file_id: str, user: dict = Depends(verify_token)):
    file_data = supabase.table("knowledge_files").select("*").eq("id", file_id).single().execute()
    if file_data.data:
        supabase.storage.from_("knowledge-files").remove([file_data.data["storage_path"]])
        supabase.table("knowledge_files").delete().eq("id", file_id).execute()
    return {"success": True}

@app.get("/knowledge/{file_id}/content")
async def get_knowledge_content(file_id: str, user: dict = Depends(verify_token)):
    file_data = supabase.table("knowledge_files").select("*").eq("id", file_id).single().execute()
    if not file_data.data:
        raise HTTPException(status_code=404, detail="File not found")
    return {"content": file_data.data.get("extracted_text", "")}

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}

@app.put("/sessions/{session_id}")
async def update_session(
    session_id: str, 
    title: str = Form(...), 
    user: dict = Depends(verify_token)
):
    try:
        result = supabase.table("chat_sessions").update({
            "title": title,
            "updated_at": datetime.now().isoformat()
        }).eq("id", session_id).eq("user_id", user["id"]).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Session not found")
        return result.data[0]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(verify_token)):
    try:
        # Delete messages first
        supabase.table("chat_messages").delete().eq("session_id", session_id).execute()
        # Delete session
        result = supabase.table("chat_sessions").delete().eq("id", session_id).eq("user_id", user["id"]).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
