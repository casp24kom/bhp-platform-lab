# app/citations.py
from typing import Dict, Any

def cite(chunk: Dict[str, Any]) -> str:
    doc_id = chunk.get("DOC_ID") or "UNKNOWN"
    doc_name = chunk.get("DOC_NAME") or "UnknownDoc"
    chunk_id = chunk.get("CHUNK_ID")
    return f"[{doc_id}|{doc_name}#chunk{chunk_id}]"