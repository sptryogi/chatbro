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
from google.oauth2 import service_account
from googleapiclient.discovery import build
import io
import base64
from rag import get_rag, QdrantRAG

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
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Models
class LoginRequest(BaseModel):
    username: str
    password: str

class ChatRequest(BaseModel):
    model: Literal["gemini", "deepseek", "groq", "openai"]
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
        # === API KEYS ===
        api_keys = {
            "gemini": GEMINI_API_KEY,
            "deepseek": DEEPSEEK_API_KEY,
            "groq": GROQ_API_KEY,
            "openai": OPENAI_API_KEY
        }
        
        if not api_keys.get(req.model):
            raise HTTPException(status_code=500, detail=f"API key for {req.model} not configured")
        
        
        # === 1. LOAD ALL USER HISTORY ===
        all_user_messages = []
        try:
            sessions = supabase.table("chat_sessions")\
                .select("id")\
                .eq("user_id", user["id"])\
                .execute()
            
            session_ids = [s["id"] for s in sessions.data] if sessions.data else []
            
            if session_ids:
                all_msgs = supabase.table("chat_messages")\
                    .select("*")\
                    .in_("session_id", session_ids)\
                    .order("created_at", desc=False)\
                    .limit(50)\
                    .execute()
                
                if all_msgs.data:
                    all_user_messages = [
                        {"role": m["role"], "content": m["content"]}
                        for m in all_msgs.data
                        if m["role"] in ["user", "assistant"]
                    ]
                    
                    logger.info(f"Loaded {len(all_user_messages)} history messages")
                    
        except Exception as e:
            logger.warning(f"History load failed: {e}")
        
        
        # === 2. RAG RETRIEVAL ===
        knowledge_context = ""
        try:
            rag = get_rag()
            
            last_user_msg = next(
                (m["content"] for m in reversed(req.messages) if m["role"] == "user"),
                ""
            )
            
            if last_user_msg:
                results = rag.search(user["id"], last_user_msg, limit=3)
                
                if results:
                    knowledge_context = "\n\n".join([
                        f"[Source: {r['source']}]\n{r['text'][:500]}..."
                        for r in results
                    ])
                    
                    logger.info(f"🔍 RAG retrieved {len(results)} chunks")
                    
        except Exception as e:
            logger.warning(f"RAG failed (non-critical): {e}")
        
        
        # === 3. BUILD SYSTEM PROMPT ===
        system_content = req.system_instruction or "You are a helpful assistant."
        
        if knowledge_context:
            system_content += f"""

RELEVANT CONTEXT FROM KNOWLEDGE BASE:
{knowledge_context}

Instructions:
- Use this context if relevant
- If not relevant, answer normally
"""
        
        
        # === 4. COMBINE MESSAGES ===
        combined_messages = [{"role": "system", "content": system_content}]
        
        current_contents = {m["content"] for m in req.messages}
        
        # Tambahkan history (hindari duplicate)
        for msg in all_user_messages:
            if msg["content"] not in current_contents:
                combined_messages.append(msg)
        
        # Tambahkan current messages
        for msg in req.messages:
            if msg["role"] != "system":
                combined_messages.append(msg)
        
        
        logger.info(f"Total messages to AI: {len(combined_messages)}")
        
        
        # === 5. ROUTING MODEL ===
        if req.model == "gemini":
            result = await chat_gemini(req, combined_messages)
        elif req.model == "deepseek":
            result = await chat_deepseek(req, combined_messages)
        elif req.model == "groq":
            result = await chat_groq(req, combined_messages)
        elif req.model == "openai":
            result = await chat_openai(req, combined_messages)
        else:
            raise HTTPException(status_code=400, detail="Invalid model")
        
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

async def chat_openai(req: ChatRequest, messages: List[dict]):
    try:
        client = OpenAI(
            api_key=OPENAI_API_KEY, 
            base_url="https://api.openai.com/v1"  # ✅ Official OpenAI API
        )
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",  # atau "gpt-4", "gpt-3.5-turbo"
            messages=messages,
            temperature=req.temperature,
            top_p=req.top_p,
            max_tokens=req.max_tokens
        )
        return {"response": response.choices[0].message.content, "model": "openai"}
    except Exception as e:
        logger.error(f"OpenAI error: {str(e)}")
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
    """
    NEW FLOW: File → Extract → Chunk → Embed → Qdrant Cloud
    (Tidak lagi simpan ke Supabase Storage untuk text content)
    """
    try:
        # Read file content
        content = await file.read()
        file_ext = file.filename.split(".")[-1].lower()
        
        # Validasi file type
        allowed = ["pdf", "docx", "doc", "txt"]
        if file_ext not in allowed:
            raise HTTPException(400, f"Only {allowed} allowed")
        
        # Process ke Qdrant
        rag = get_rag()
        result = rag.process_and_upload(
            user_id=user["id"],
            file_content=content,
            filename=file.filename,
            file_type=file_ext
        )
        
        # Simpan metadata ke Supabase (untuk UI listing saja)
        # Tidak perlu extracted_text lagi karena sudah di Qdrant
        knowledge_meta = supabase.table("knowledge_files").insert({
            "user_id": user["id"],
            "filename": file.filename,
            "original_name": file.filename,
            "file_type": file_ext,
            "file_size": len(content),
            "storage_path": f"qdrant://{result['collection']}",  # Marker bahwa di Qdrant
            "extracted_text": result["text_preview"],  # Preview saja
            "chunks_count": result["chunks_uploaded"],
            "metadata": {
                "qdrant_collection": result["collection"],
                "vectors_count": result["total_points"]
            }
        }).execute()
        
        return {
            "success": True,
            "file": knowledge_meta.data[0],
            "rag_result": {
                "collection": result["collection"],
                "chunks": result["chunks_uploaded"],
                "preview": result["text_preview"]
            }
        }
        
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/knowledge")
async def get_knowledge(user: dict = Depends(verify_token)):
    files = supabase.table("knowledge_files").select("*").eq("user_id", user["id"]).execute()
    return files.data

@app.delete("/knowledge/{file_id}")
async def delete_knowledge(file_id: str, user: dict = Depends(verify_token)):
    """Delete dari Supabase metadata + Qdrant vectors"""
    try:
        # Get file info
        file_data = supabase.table("knowledge_files").select("*").eq("id", file_id).eq("user_id", user["id"]).single().execute()
        
        if not file_data.data:
            raise HTTPException(404, "File not found")
        
        filename = file_data.data["original_name"]
        
        # Delete dari Qdrant
        try:
            rag = get_rag()
            rag.delete_file_vectors(user["id"], filename)
        except Exception as e:
            logger.warning(f"Qdrant delete failed: {e}")
        
        # Delete dari Supabase
        supabase.table("knowledge_files").delete().eq("id", file_id).execute()
        
        return {"success": True, "deleted": filename}
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, str(e))

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

GOOGLE_DRIVE_CREDENTIALS = os.getenv("GOOGLE_DRIVE_CREDENTIALS")  # JSON string

@app.post("/knowledge/drive")
async def upload_from_drive(
    file_id: str = Form(...),
    filename: str = Form(...),  # Tambah filename dari frontend
    user: dict = Depends(verify_token)
):
    """
    Import dari Google Drive langsung ke Qdrant
    """
    try:
        # Setup Google Drive API
        creds_info = json.loads(GOOGLE_DRIVE_CREDENTIALS)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=credentials)
        
        # Download file
        request = service.files().get_media(fileId=file_id)
        
        from googleapiclient.http import MediaIoBaseDownload
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        content = fh.getvalue()
        file_ext = filename.split(".")[-1].lower()
        
        # Process ke Qdrant (sama dengan upload biasa)
        rag = get_rag()
        result = rag.process_and_upload(
            user_id=user["id"],
            file_content=content,
            filename=filename,
            file_type=file_ext
        )
        
        # Simpan metadata
        knowledge_meta = supabase.table("knowledge_files").insert({
            "user_id": user["id"],
            "filename": f"gdrive://{file_id}",
            "original_name": filename,
            "file_type": file_ext,
            "file_size": len(content),
            "storage_path": f"qdrant://{result['collection']}",
            "extracted_text": result["text_preview"],
            "chunks_count": result["chunks_uploaded"],
            "metadata": {
                "source": "google_drive",
                "drive_file_id": file_id,
                "qdrant_collection": result["collection"]
            }
        }).execute()
        
        return {
            "success": True,
            "file": knowledge_meta.data[0],
            "source": "google_drive",
            "rag_result": result
        }
        
    except Exception as e:
        logger.error(f"Drive import error: {e}")
        raise HTTPException(500, str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
