import os
import json
import logging
from typing import Dict, List, Any
from dotenv import load_dotenv
import asyncio
import time
from functools import wraps

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def retrieve_information(query: str) -> Dict:
    """
    Retrieve information from the knowledge base based on a query
    """
    from retrieving import RAGRetriever
    retriever = RAGRetriever()

    try:
        # Call the existing retrieve method from the RAGRetriever instance
        # Use lower threshold for fallback compatibility
        json_response = retriever.retrieve(query_text=query, top_k=5, threshold=0.0)
        results = json.loads(json_response)

        # Format the results for the assistant
        formatted_results = []
        for result in results.get('results', []):
            formatted_results.append({
                'content': result['content'],
                'url': result['url'],
                'position': result['position'],
                'similarity_score': result['similarity_score']
            })

        return {
            'query': query,
            'retrieved_chunks': formatted_results,
            'total_results': len(formatted_results)
        }
    except Exception as e:
        logger.error(f"Error in retrieve_information: {e}")
        return {
            'query': query,
            'retrieved_chunks': [],
            'total_results': 0,
            'error': str(e)
        }

class RAGAgent:
    def __init__(self):
        """Initialize RAG Agent with retrieval capability"""
        logger.info("RAG Agent initialized")

    def query_agent(self, query_text: str) -> Dict:
        """
        Process a query through the RAG agent and return structured response
        """
        start_time = time.time()

        logger.info(f"Processing query through RAG agent: '{query_text[:50]}...'")

        try:
            # Retrieve relevant information
            retrieval_result = retrieve_information(query_text)

            matched_chunks = retrieval_result.get('retrieved_chunks', [])

            # Extract sources from matched chunks
            sources = list(set([chunk['url'] for chunk in matched_chunks if chunk.get('url')]))

            # Format the context for the LLM
            context = self._format_context(matched_chunks, query_text)

            # Generate answer using the context
            answer = self._generate_answer(query_text, context, matched_chunks)

            # Calculate query time
            query_time_ms = (time.time() - start_time) * 1000

            response = {
                "answer": answer,
                "sources": sources,
                "matched_chunks": matched_chunks,
                "query_time_ms": query_time_ms,
                "confidence": self._calculate_confidence(matched_chunks)
            }

            logger.info(f"Query processed in {query_time_ms:.2f}ms")
            return response

        except Exception as e:
            logger.error(f"Error processing query: {e}")
            return {
                "answer": "Sorry, I encountered an error processing your request.",
                "sources": [],
                "matched_chunks": [],
                "error": str(e),
                "query_time_ms": (time.time() - start_time) * 1000
            }

    def _format_context(self, matched_chunks: List[Dict], query: str) -> str:
        """Format matched chunks into context string"""
        if not matched_chunks:
            return f"No relevant information found for: {query}"

        context_parts = [f"Based on the following information relevant to '{query}':"]

        for i, chunk in enumerate(matched_chunks, 1):
            content = chunk.get('content', '')
            url = chunk.get('url', '')
            score = chunk.get('similarity_score', 0)

            context_parts.append(f"\n[Source {i}] (Relevance: {score:.2%})")
            context_parts.append(f"From: {url}")
            context_parts.append(f"Content: {content[:300]}...")

        return "\n".join(context_parts)

    def _generate_answer(self, query: str, context: str, matched_chunks: List[Dict]) -> str:
        """Generate answer based on retrieved context"""
        if not matched_chunks:
            return f"I couldn't find specific information about '{query}' in the textbook. Please try rephrasing your question or search for related topics."

        # Build a simple answer from the context
        top_chunk = matched_chunks[0] if matched_chunks else None

        if top_chunk:
            content = top_chunk.get('content', '')
            url = top_chunk.get('url', '')

            answer = f"{content}\n\n📚 Source: {url}"
            return answer

        return "I found some relevant information but couldn't generate a clear answer. Please try another question."

    def _calculate_confidence(self, matched_chunks: List[Dict]) -> str:
        """
        Calculate confidence level based on similarity scores and number of matches
        """
        if not matched_chunks:
            return "low"

        avg_score = sum(chunk.get('similarity_score', 0.0) for chunk in matched_chunks) / len(matched_chunks)

        if avg_score >= 0.7:
            return "high"
        elif avg_score >= 0.4:
            return "medium"
        else:
            return "low"

def query_agent(query_text: str) -> Dict:
    """
    Convenience function to query the RAG agent
    """
    agent = RAGAgent()
    return agent.query_agent(query_text)

def run_agent_sync(query_text: str) -> Dict:
    """
    Synchronous function to run the agent for direct usage
    """
    import asyncio

    async def run_async():
        agent = RAGAgent()
        return await agent._async_query_agent(query_text)

    # Check if there's already a running event loop
    try:
        loop = asyncio.get_running_loop()
        # If there's already a loop, run in a separate thread
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, run_async())
            return future.result()
    except RuntimeError:
        # No running loop, safe to use asyncio.run
        return asyncio.run(run_async())

def main():
    """
    Main function to demonstrate the RAG agent functionality
    """
    logger.info("Initializing RAG Agent...")

    # Initialize the agent
    agent = RAGAgent()

    # Example queries to test the system
    test_queries = [
        "What is ROS2?",
        "Explain humanoid design principles",
        "How does VLA work?",
        "What are simulation techniques?",
        "Explain AI control systems"
    ]

    print("RAG Agent - Testing Queries")
    print("=" * 50)

    for i, query in enumerate(test_queries, 1):
        print(f"\nQuery {i}: {query}")
        print("-" * 30)

        # Process query through agent
        response = agent.query_agent(query)

        # Print formatted results
        print(f"Answer: {response['answer']}")

        if response.get('sources'):
            print(f"Sources: {len(response['sources'])} documents")
            for source in response['sources'][:3]:  # Show first 3 sources
                print(f"  - {source}")

        if response.get('matched_chunks'):
            print(f"Matched chunks: {len(response['matched_chunks'])}")
            for j, chunk in enumerate(response['matched_chunks'][:2], 1):  # Show first 2 chunks
                content_preview = chunk['content'][:100] + "..." if len(chunk['content']) > 100 else chunk['content']
                print(f"  Chunk {j}: {content_preview}")
                print(f"    Source: {chunk['url']}")
                print(f"    Score: {chunk['similarity_score']:.3f}")

        print(f"Query time: {response['query_time_ms']:.2f}ms")
        print(f"Confidence: {response.get('confidence', 'unknown')}")

        if i < len(test_queries):  # Don't sleep after the last query
            time.sleep(1)  # Small delay between queries

if __name__ == "__main__":
    main()