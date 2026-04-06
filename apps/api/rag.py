"""
RAG Module dengan Qdrant Cloud - Hybrid Search (Dense + Sparse)
"""
import os
import logging
from typing import List, Dict, Any
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, SparseVectorParams, 
    SparseIndexParams, PointStruct, Prefetch
)
from fastembed import SparseTextEmbedding

logger = logging.getLogger(__name__)

# Config dari Environment Variables
QDRANT_URL = os.getenv("QDRANT_URL")  # Contoh: https://xxx.gcp.cloud.qdrant.io
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "chatbro_knowledge")

DENSE_VECTOR_NAME = "dense"
SPARSE_VECTOR_NAME = "sparse"

class QdrantRAG:
    def __init__(self):
        self.client = None
        self.dense_embed = None
        self.sparse_embed = None
        self._init_client()
    
    def _init_client(self):
        """Inisialisasi koneksi ke Qdrant Cloud"""
        try:
            self.client = QdrantClient(url=QDRANT_URL, api_key=QDRANT_API_KEY)
            self.dense_embed = HuggingFaceEmbeddings(
                model_name="intfloat/multilingual-e5-small"
            )
            self.sparse_embed = SparseTextEmbedding(model_name="Qdrant/bm25")
            logger.info("✅ Qdrant RAG initialized")
        except Exception as e:
            logger.error(f"❌ Failed to init Qdrant: {e}")
            raise
    
    def ensure_collection(self, user_id: str):
        """
        Buat collection per user atau gunakan collection global dengan user_id filter
        Rekomendasi: Collection global dengan metadata filtering (lebih scalable)
        """
        collection_name = f"{COLLECTION_NAME}_{user_id}"  # Per-user collection
        
        try:
            collections = self.client.get_collections()
            exists = any(c.name == collection_name for c in collections.collections)
            
            if not exists:
                logger.info(f"📦 Creating collection: {collection_name}")
                self.client.create_collection(
                    collection_name=collection_name,
                    vectors_config={
                        DENSE_VECTOR_NAME: VectorParams(
                            size=384,  # multilingual-e5-small dimension
                            distance=Distance.COSINE
                        )
                    },
                    sparse_vectors_config={
                        SPARSE_VECTOR_NAME: SparseVectorParams(
                            index=SparseIndexParams(on_disk=False)
                        )
                    }
                )
                logger.info(f"✅ Collection created: {collection_name}")
            
            return collection_name
            
        except Exception as e:
            logger.error(f"❌ Error ensuring collection: {e}")
            raise
    
    def process_and_upload(
        self, 
        user_id: str, 
        file_content: bytes, 
        filename: str,
        file_type: str
    ) -> Dict[str, Any]:
        """
        Pipeline: File → Extract Text → Chunk → Embed → Upload ke Qdrant
        """
        try:
            # 1. Extract text dari file
            text = self._extract_text(file_content, file_type, filename)
            if not text or len(text.strip()) == 0:
                raise ValueError("No text content extracted from file")
            
            logger.info(f"📄 Extracted {len(text)} chars from {filename}")
            
            # 2. Split chunks
            chunks = self._split_text(text, filename)
            logger.info(f"✂️ Split into {len(chunks)} chunks")
            
            # 3. Ensure collection exists
            collection_name = self.ensure_collection(user_id)
            
            # 4. Generate embeddings
            dense_vectors = self.dense_embed.embed_documents(chunks)
            sparse_vectors = list(self.sparse_embed.embed(chunks))
            logger.info(f"🧠 Generated {len(dense_vectors)} embeddings")
            
            # 5. Prepare points dengan metadata
            # Get current count untuk ID offset
            try:
                collection_info = self.client.get_collection(collection_name)
                start_id = collection_info.points_count
            except:
                start_id = 0
            
            points = []
            for idx, (chunk, dense_vec, sparse_vec) in enumerate(zip(chunks, dense_vectors, sparse_vectors)):
                point = PointStruct(
                    id=start_id + idx,
                    vector={
                        DENSE_VECTOR_NAME: dense_vec,
                        SPARSE_VECTOR_NAME: sparse_vec.as_object()
                    },
                    payload={
                        "text": chunk,
                        "chunk_id": idx,
                        "source": filename,
                        "user_id": user_id,  # Untuk filtering
                        "total_chunks": len(chunks),
                        "file_type": file_type
                    }
                )
                points.append(point)
            
            # 6. Upload ke Qdrant (batch)
            batch_size = 50
            for i in range(0, len(points), batch_size):
                batch = points[i:i+batch_size]
                self.client.upsert(
                    collection_name=collection_name,
                    points=batch
                )
                logger.info(f"📤 Uploaded batch {i//batch_size + 1}/{(len(points)-1)//batch_size + 1}")
            
            # 7. Verifikasi
            final_info = self.client.get_collection(collection_name)
            
            return {
                "success": True,
                "collection": collection_name,
                "filename": filename,
                "chunks_uploaded": len(points),
                "total_points": final_info.points_count,
                "text_preview": text[:200] + "..." if len(text) > 200 else text
            }
            
        except Exception as e:
            logger.error(f"❌ Process and upload error: {e}")
            raise
    
    def _extract_text(self, content: bytes, file_type: str, filename: str) -> str:
        """Extract text dari berbagai file types"""
        import io
        
        text = ""
        file_ext = filename.split(".")[-1].lower()
        
        try:
            if file_ext == "txt":
                text = content.decode("utf-8")
                
            elif file_ext == "pdf":
                from PyPDF2 import PdfReader
                pdf = PdfReader(io.BytesIO(content))
                for page in pdf.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
                        
            elif file_ext in ["docx", "doc"]:
                import docx2txt
                # Simpan temporary untuk docx2txt
                temp_path = f"/tmp/{filename}"
                with open(temp_path, 'wb') as f:
                    f.write(content)
                text = docx2txt.process(temp_path)
                os.remove(temp_path) if os.path.exists(temp_path) else None
                
            else:
                # Fallback: coba decode sebagai text
                try:
                    text = content.decode("utf-8")
                except:
                    raise ValueError(f"Unsupported file type: {file_ext}")
            
            return text
            
        except Exception as e:
            logger.error(f"Text extraction error: {e}")
            raise
    
    def _split_text(self, text: str, source: str) -> List[str]:
        """Split text menjadi chunks dengan overlap"""
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
            length_function=len
        )
        
        # Tambah metadata source ke setiap chunk untuk tracing
        chunks = splitter.split_text(text)
        
        # Tambah header ke chunk pertama untuk konteks
        if chunks:
            chunks[0] = f"=== SOURCE: {source} ===\n\n{chunks[0]}"
        
        return chunks
    
    def search(
        self, 
        user_id: str, 
        query: str, 
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Hybrid Search: Dense (semantic) + Sparse (keyword/BM25)
        """
        try:
            collection_name = f"{COLLECTION_NAME}_{user_id}"
            
            # Generate query embeddings
            dense_query = self.dense_embed.embed_query(query)
            sparse_query = list(self.sparse_embed.query_embed(query))[0]
            
            # Hybrid search dengan prefetch
            results = self.client.query_points(
                collection_name=collection_name,
                prefetch=[
                    Prefetch(query=dense_query, using=DENSE_VECTOR_NAME, limit=limit*2),
                    Prefetch(query=sparse_query.as_object(), using=SPARSE_VECTOR_NAME, limit=limit*2),
                ],
                query=dense_query,
                using=DENSE_VECTOR_NAME,
                limit=limit,
                with_payload=True,
                # Filter berdasarkan user_id untuk security
                query_filter={
                    "must": [
                        {"key": "user_id", "match": {"value": user_id}}
                    ]
                }
            )
            
            # Format hasil
            documents = []
            for point in results.points:
                documents.append({
                    "text": point.payload.get("text", ""),
                    "source": point.payload.get("source", ""),
                    "chunk_id": point.payload.get("chunk_id"),
                    "score": point.score,
                    "id": point.id
                })
            
            logger.info(f"🔍 Search '{query[:30]}...' found {len(documents)} results")
            return documents
            
        except Exception as e:
            logger.error(f"❌ Search error: {e}")
            # Kalau collection tidak ada, return empty
            if "Not found" in str(e) or "doesn't exist" in str(e):
                return []
            raise
    
    def delete_file_vectors(self, user_id: str, filename: str) -> bool:
        """Hapus semua vectors dari file tertentu"""
        try:
            collection_name = f"{COLLECTION_NAME}_{user_id}"
            
            self.client.delete(
                collection_name=collection_name,
                points_selector={
                    "filter": {
                        "must": [
                            {"key": "user_id", "match": {"value": user_id}},
                            {"key": "source", "match": {"value": filename}}
                        ]
                    }
                }
            )
            
            logger.info(f"🗑️ Deleted vectors for {filename}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Delete error: {e}")
            return False
    
    def get_stats(self, user_id: str) -> Dict[str, Any]:
        """Get collection stats untuk user"""
        try:
            collection_name = f"{COLLECTION_NAME}_{user_id}"
            info = self.client.get_collection(collection_name)
            
            return {
                "collection": collection_name,
                "points_count": info.points_count,
                "status": str(info.status)
            }
        except:
            return {
                "collection": collection_name,
                "points_count": 0,
                "status": "not_found"
            }

# Singleton instance
_rag_instance = None

def get_rag() -> QdrantRAG:
    """Get atau buat RAG instance"""
    global _rag_instance
    if _rag_instance is None:
        _rag_instance = QdrantRAG()
    return _rag_instance
