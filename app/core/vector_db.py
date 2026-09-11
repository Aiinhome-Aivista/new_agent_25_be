import chromadb
from chromadb.config import Settings
import os

# Use a local directory to store ChromaDB data
CHROMA_DATA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "chroma_data")

# Initialize persistent client
chroma_client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)

def get_standards_collection():
    """
    Get or create the ChromaDB collection for coding standards.
    """
    # Create or get collection
    # We use the default embedding function (sentence-transformers)
    return chroma_client.get_or_create_collection(
        name="coding_standards",
        metadata={"hnsw:space": "cosine"}
    )
