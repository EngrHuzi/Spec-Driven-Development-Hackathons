import os
import json
from typing import List, Dict, Any
import cohere
from qdrant_client import QdrantClient
from qdrant_client.http import models
import logging
from dotenv import load_dotenv
import time

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RAGRetriever:
    def __init__(self):
        # Initialize Cohere client
        self.cohere_client = cohere.Client(api_key=os.getenv("COHERE_API_KEY"))

        # Initialize Qdrant client with fallback to in-memory storage
        qdrant_url = os.getenv("QDRANT_URL", "http://localhost:6333")
        qdrant_api_key = os.getenv("QDRANT_API_KEY")

        self.qdrant_available = False
        # Always load sample data for fallback
        self._load_sample_data()

        try:
            if qdrant_api_key:
                self.qdrant_client = QdrantClient(url=qdrant_url, api_key=qdrant_api_key)
            else:
                self.qdrant_client = QdrantClient(url=qdrant_url)
            # Test connection
            self.qdrant_client.get_collections()
            self.qdrant_available = True
            logger.info("Connected to Qdrant successfully")
        except Exception as e:
            logger.warning(f"Could not connect to Qdrant: {e}. Using in-memory fallback with sample data.")
            self.qdrant_client = None
            self.qdrant_available = False

        # Default collection name
        self.collection_name = "rag_embedding"

    def _load_sample_data(self):
        """Load sample textbook content for fallback when Qdrant is unavailable"""
        self.sample_data = [
            {
                "content": "ROS 2 (Robot Operating System 2) is a flexible middleware for writing robot software. It's built on a publish-subscribe model where nodes communicate through topics and services. ROS 2 provides tools for hardware abstraction, message-passing between processes, package management, and more.",
                "url": "/docs/02-ros-foundations/ros2-basics",
                "position": 0,
                "keywords": ["ROS 2", "Robot Operating System", "middleware", "publish-subscribe"]
            },
            {
                "content": "Humanoid robotics involves designing robots that mimic human form and movement. Key principles include bipedal locomotion, dexterous manipulation, perception systems, and balance control. Modern humanoids use advanced sensors, actuators, and AI for autonomous operation.",
                "url": "/docs/07-humanoid-design/principles",
                "position": 1,
                "keywords": ["humanoid", "bipedal", "locomotion", "manipulation", "balance"]
            },
            {
                "content": "Physical AI combines robotics, computer vision, and machine learning to enable robots to understand and interact with the physical world. It involves perception, planning, control, and learning systems working together in real-world environments.",
                "url": "/docs/01-fundamentals/physical-ai-overview",
                "position": 0,
                "keywords": ["Physical AI", "robotics", "vision", "machine learning", "control"]
            },
            {
                "content": "Vision-Language-Action (VLA) models are multimodal AI systems that can understand images and language to generate robot actions. They learn from demonstrations and can perform complex manipulation tasks through end-to-end learning.",
                "url": "/docs/05-vision-language-action/overview",
                "position": 0,
                "keywords": ["VLA", "vision", "language", "action", "multimodal"]
            },
            {
                "content": "Simulation in robotics allows testing and development without hardware. Tools like Gazebo and IsaacGym provide physics simulation, sensor simulation, and visualization. Simulation helps with algorithm development, testing, and training machine learning models.",
                "url": "/docs/03-simulation/overview",
                "position": 0,
                "keywords": ["simulation", "Gazebo", "IsaacGym", "physics", "testing"]
            },
            {
                "content": "Robot control systems use feedback loops to regulate motion and interaction with the environment. PID control, trajectory planning, force control, and impedance control are common techniques. Control systems must handle real-time constraints and disturbances.",
                "url": "/docs/06-advanced-control/basics",
                "position": 0,
                "keywords": ["control", "PID", "trajectory", "feedback", "disturbance"]
            }
        ]

    def get_embedding(self, text: str) -> List[float]:
        """
        Generate embedding for query text using Cohere
        """
        try:
            response = self.cohere_client.embed(
                texts=[text],
                model="embed-multilingual-v3.0",  # Using same model as storage
                input_type="search_query"  # Optimize for search queries
            )
            return response.embeddings[0]  # Return the first (and only) embedding
        except Exception as e:
            logger.error(f"Error generating embedding for query: {e}")
            return []

    def _query_fallback(self, query_text: str, top_k: int = 5) -> List[Dict]:
        """
        Fallback search using keyword matching when Qdrant is unavailable
        """
        query_lower = query_text.lower()
        scored_results = []

        for item in self.sample_data:
            score = 0.0
            content = item.get("content", "").lower()

            # Keyword matching
            for keyword in item.get("keywords", []):
                if keyword.lower() in query_lower:
                    score += 0.3

            # Content matching
            words = query_text.lower().split()
            for word in words:
                if len(word) > 3:  # Only meaningful words
                    if word in content:
                        score += 0.1

            if score > 0:
                result = {
                    "content": item["content"],
                    "url": item["url"],
                    "position": item.get("position", 0),
                    "similarity_score": min(score, 0.95),  # Cap at 0.95
                    "chunk_id": hash(item["content"]) % 10000,
                    "created_at": "2025-12-16"
                }
                scored_results.append(result)

        # Sort by score descending
        scored_results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return scored_results[:top_k]

    def query_qdrant(self, query_text: str, top_k: int = 5, threshold: float = 0.0) -> List[Dict]:
        """
        Query Qdrant for similar vectors and return results with metadata
        Falls back to keyword search if Qdrant is unavailable
        """
        if not self.qdrant_available:
            logger.info("Using fallback search")
            return self._query_fallback(query_text, top_k)

        try:
            # Perform similarity search in Qdrant
            search_results = self.qdrant_client.search(
                collection_name=self.collection_name,
                query_vector=query_text,
                limit=top_k,
                score_threshold=threshold,
                with_payload=True  # Include metadata with results
            )

            # Format results
            formatted_results = []
            for result in search_results:
                formatted_result = {
                    "content": result.payload.get("content", ""),
                    "url": result.payload.get("url", ""),
                    "position": result.payload.get("position", 0),
                    "similarity_score": result.score,
                    "chunk_id": result.id,
                    "created_at": result.payload.get("created_at", "")
                }
                formatted_results.append(formatted_result)

            return formatted_results

        except Exception as e:
            logger.error(f"Error querying Qdrant: {e}. Falling back to keyword search.")
            return self._query_fallback(query_text, top_k)

    def verify_content_accuracy(self, retrieved_chunks: List[Dict]) -> bool:
        """
        Verify that retrieved content matches original stored text (basic validation)
        """
        # In a real implementation, this would compare against original sources
        # For now, we'll validate that required fields exist and have content
        for chunk in retrieved_chunks:
            if not chunk.get("content") or not chunk.get("url"):
                logger.warning(f"Missing content or URL in chunk: {chunk.get('chunk_id')}")
                return False

        # Additional validation could include checking content length, URL format, etc.
        return True

    def format_json_response(self, results: List[Dict], query: str, query_time_ms: float) -> str:
        """
        Format retrieval results into clean JSON response
        """
        response = {
            "query": query,
            "results": results,
            "metadata": {
                "query_time_ms": query_time_ms,
                "total_results": len(results),
                "timestamp": time.time(),
                "collection_name": self.collection_name
            }
        }

        return json.dumps(response, indent=2)

    def retrieve(self, query_text: str, top_k: int = 5, threshold: float = 0.0, include_metadata: bool = True) -> str:
        """
        Main retrieval function that orchestrates the complete workflow
        """
        start_time = time.time()

        logger.info(f"Processing retrieval request for query: '{query_text[:50]}...'")

        # Step 1: Convert query text to embedding (if Qdrant is available)
        query_embedding = None
        if self.qdrant_available:
            query_embedding = self.get_embedding(query_text)
            if not query_embedding:
                error_response = {
                    "query": query_text,
                    "results": [],
                    "error": "Failed to generate query embedding",
                    "metadata": {
                        "query_time_ms": (time.time() - start_time) * 1000,
                        "timestamp": time.time()
                    }
                }
                return json.dumps(error_response, indent=2)

        # Step 2: Query Qdrant for similar vectors (or use fallback)
        raw_results = self.query_qdrant(query_text, top_k, threshold)

        if not raw_results:
            logger.warning("No results returned from Qdrant")

        # Step 3: Verify content accuracy (optional)
        if include_metadata:
            is_accurate = self.verify_content_accuracy(raw_results)
            if not is_accurate:
                logger.warning("Content accuracy verification failed for some results")

        # Step 4: Calculate total query time
        query_time_ms = (time.time() - start_time) * 1000

        # Step 5: Format response as JSON
        json_response = self.format_json_response(raw_results, query_text, query_time_ms)

        logger.info(f"Retrieval completed in {query_time_ms:.2f}ms, {len(raw_results)} results returned")

        return json_response

def retrieve_all_data():
    """
    Function to retrieve and display all data from Qdrant collection
    """
    logger.info("Initializing RAG Retriever to fetch all data...")

    # Initialize the retriever
    retriever = RAGRetriever()

    print("RAG Retrieval System - All Stored Data")
    print("=" * 50)

    try:
        # Get all points from the collection using scroll
        points = []
        offset = None
        while True:
            # Scroll through the collection to get all points
            batch, next_offset = retriever.qdrant_client.scroll(
                collection_name=retriever.collection_name,
                limit=1000,  # Get up to 1000 points at a time
                offset=offset,
                with_payload=True,
                with_vectors=False
            )

            points.extend(batch)

            # If next_offset is None, we've reached the end
            if next_offset is None:
                break

            offset = next_offset

        print(f"Total stored chunks: {len(points)}")
        print("-" * 50)

        for i, point in enumerate(points, 1):
            payload = point.payload
            content_preview = ''.join(char for char in payload.get("content", "")[:200] if ord(char) < 256)

            print(f"Chunk {i}:")
            print(f"  ID: {point.id}")
            print(f"  URL: {payload.get('url', 'N/A')}")
            print(f"  Position: {payload.get('position', 'N/A')}")
            print(f"  Content Preview: {content_preview}...")
            print(f"  Created At: {payload.get('created_at', 'N/A')}")
            print("-" * 30)

    except Exception as e:
        logger.error(f"Error retrieving all data: {e}")
        print(f"Error retrieving all data: {e}")


def main():
    """
    Main function to demonstrate the retrieval functionality
    """
    import sys

    logger.info("Initializing RAG Retriever...")

    # Check if user wants to retrieve all data or run queries
    if len(sys.argv) > 1 and sys.argv[1] == "all":
        retrieve_all_data()
        return

    # Initialize the retriever
    retriever = RAGRetriever()

    # Example queries to test the system
    test_queries = [
        "What is ROS2?",
        "Explain humanoid design principles",
        "How does VLA work?",
        "What are simulation techniques?",
        "Explain AI control systems"
    ]

    print("RAG Retrieval System - Testing Queries")
    print("=" * 50)

    for i, query in enumerate(test_queries, 1):
        print(f"\nQuery {i}: {query}")
        print("-" * 30)

        # Retrieve results
        json_response = retriever.retrieve(query, top_k=3)
        response_dict = json.loads(json_response)

        # Print formatted results
        results = response_dict.get("results", [])
        if results:
            for j, result in enumerate(results, 1):
                print(f"Result {j} (Score: {result['similarity_score']:.3f}):")
                print(f"  URL: {result['url']}")
                content_preview = result['content'][:100].encode('utf-8', errors='ignore').decode('utf-8')
                # Safely print content preview by removing problematic characters
                safe_content = ''.join(char for char in content_preview if ord(char) < 256)
                print(f"  Content Preview: {safe_content}...")
                print(f"  Position: {result['position']}")
                print()
        else:
            print("No results found for this query.")

        print(f"Query time: {response_dict['metadata']['query_time_ms']:.2f}ms")
        print(f"Total results: {response_dict['metadata']['total_results']}")

if __name__ == "__main__":
    main()