from typing import List, Dict, Any, Optional
import json
from app.core.vector_db import get_standards_collection
from app.core.logging_config import logger



class StandardsStore:
    """RAG repository for enterprise coding standards and best-practice rules using ChromaDB."""

    def __init__(self):
        try:
            self.collection = get_standards_collection()
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB collection: {e}")
            self.collection = None

    def sync_from_db(self):
        """Seed ChromaDB from MySQL if empty."""
        if not self.collection:
            return

        try:
            if self.collection.count() == 0:
                logger.info("ChromaDB is empty. Attempting to sync from MySQL...")
                from app.core.database import SessionLocal
                from app.models.entities import CodingStandard
                
                if not SessionLocal:
                    logger.warning("SessionLocal not available, cannot sync from DB.")
                    return
                    
                db = SessionLocal()
                db_standards = db.query(CodingStandard).all()
                
                if db_standards:
                    logger.info(f"Found {len(db_standards)} standards in MySQL. Seeding ChromaDB...")
                    for std in db_standards:
                        std_dict = {
                            "rule_code": std.rule_code,
                            "language": std.language,
                            "framework": std.framework,
                            "category": std.category,
                            "title": std.title,
                            "description": std.description,
                            "bad_example": std.bad_example or "",
                            "good_example": std.good_example or "",
                            "severity": std.severity,
                            "is_blocking": std.is_blocking,
                            "version": std.version
                        }
                        self.add_standard(std_dict)
                else:
                    logger.info("MySQL has no standards. ChromaDB remains empty.")
                db.close()
        except Exception as e:
            logger.error(f"Error syncing standards from DB: {e}")

    def search_relevant_standards(self, language: str = "java", framework: str = "spring-boot", query: str = "") -> List[Dict[str, Any]]:
        """Retrieves matching approved standards based on language, framework, and diff content from ChromaDB."""
        if not self.collection:
            logger.warning("ChromaDB collection unavailable, returning empty list.")
            return []

        where_filter = {}
        if language and language.lower() not in ("all", "general", ""):
             where_filter["language"] = language.lower()

        # Build query texts. If no query, just use language/framework as query to get some results.
        query_texts = [query] if query else [f"coding standards best practices for {language} {framework}"]

        try:
            # Query ChromaDB
            results = self.collection.query(
                query_texts=query_texts,
                n_results=5,
                where=where_filter if where_filter else None
            )

            standards = []
            if results and results.get("metadatas") and results["metadatas"][0]:
                for metadata in results["metadatas"][0]:
                    # Convert string booleans back to bool
                    if "is_blocking" in metadata:
                        metadata["is_blocking"] = str(metadata["is_blocking"]).lower() == 'true'
                    standards.append(metadata)
            
            return standards
        except Exception as e:
            logger.error(f"Error querying ChromaDB: {e}")
            return []

    def add_standard(self, standard: Dict[str, Any]) -> None:
        if not self.collection:
            return

        rule_code = standard.get("rule_code")
        if not rule_code:
            return

        # Prepare text for embedding
        document = f"Title: {standard.get('title', '')}\nCategory: {standard.get('category', '')}\nDescription: {standard.get('description', '')}\nBad Example: {standard.get('bad_example', '')}\nGood Example: {standard.get('good_example', '')}"
        
        # Prepare metadata (ensure all values are primitives like str, int, float)
        metadata = {
            "rule_code": rule_code,
            "language": (standard.get("language") or "general").lower(),
            "framework": (standard.get("framework") or "general").lower(),
            "category": (standard.get("category") or "quality").lower(),
            "title": standard.get("title", ""),
            "description": standard.get("description", ""),
            "bad_example": standard.get("bad_example", ""),
            "good_example": standard.get("good_example", ""),
            "severity": standard.get("severity", "WARNING"),
            "is_blocking": str(standard.get("is_blocking", False))
        }

        try:
            self.collection.upsert(
                ids=[rule_code],
                documents=[document],
                metadatas=[metadata]
            )
            logger.info(f"Added/Updated standard in ChromaDB: {rule_code}")
        except Exception as e:
            logger.error(f"Failed to add standard to ChromaDB: {e}")
            
    def get_all_standards(self) -> List[Dict[str, Any]]:
        """Retrieve all rules for the frontend Knowledge Base UI."""
        if not self.collection:
            return []
        
        try:
            results = self.collection.get()
            standards = []
            if results and results.get("metadatas"):
                for metadata in results["metadatas"]:
                    if "is_blocking" in metadata:
                        metadata["is_blocking"] = str(metadata["is_blocking"]).lower() == 'true'
                    standards.append(metadata)
            return standards
        except Exception as e:
            logger.error(f"Error getting all standards from ChromaDB: {e}")
            return []
            
    def delete_standard(self, rule_code: str) -> bool:
        if not self.collection:
            return False
            
        try:
            self.collection.delete(ids=[rule_code])
            return True
        except Exception as e:
            logger.error(f"Error deleting standard from ChromaDB: {e}")
            return False

standards_store = StandardsStore()
