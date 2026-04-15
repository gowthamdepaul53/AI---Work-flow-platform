"""
rag_engine.py
-------------
Retrieval-Augmented Generation pipeline.

Flow:
  1. Embed query with OpenAI text-embedding-3-small
  2. Retrieve top-k chunks from ChromaDB
  3. Inject chunks into LLM context as grounding
  4. Return answer + source citations

Used by: PlannerAgent routing → RAG step → SummarizerAgent
"""

import os
import logging
from typing import Optional

import chromadb
from chromadb.utils import embedding_functions
from langchain_openai import ChatOpenAI
from langchain.schema import HumanMessage, SystemMessage
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

SYSTEM_PROMPT = """You are a helpful assistant. Answer the user's question using ONLY
the provided context chunks. If the context is insufficient, say so clearly.
Always cite the source document name in your answer."""


class RAGEngine:
    """
    Semantic search + grounded generation over a ChromaDB vector store.

    Interview talking points:
      - Embeddings: OpenAI text-embedding-3-small (1536 dims, cost-efficient)
      - Vector DB: ChromaDB — runs embedded (no infra) or as a server
      - Retrieval: cosine similarity, top-k=5 by default
      - Swap-ready: replace ChromaDB client with Pinecone/Weaviate in one place
    """

    def __init__(
        self,
        collection_name: str = "support_docs",
        chroma_host: str = "localhost",
        chroma_port: int = 8001,
        top_k: int = 5,
    ):
        self.top_k = top_k
        self.collection_name = collection_name

        # OpenAI embedding function (used for both indexing and querying)
        self.embed_fn = embedding_functions.OpenAIEmbeddingFunction(
            api_key=os.getenv("OPENAI_API_KEY"),
            model_name="text-embedding-3-small",
        )

        # ChromaDB client — connects to Docker container in production
        self.client = chromadb.HttpClient(host=chroma_host, port=chroma_port)
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            embedding_function=self.embed_fn,
            metadata={"hnsw:space": "cosine"},
        )

        self.llm = ChatOpenAI(
            model="gpt-4",
            temperature=0.1,
            openai_api_key=os.getenv("OPENAI_API_KEY"),
        )

        logger.info(f"[RAGEngine] Connected to collection '{collection_name}'")

    # ------------------------------------------------------------------
    # Indexing
    # ------------------------------------------------------------------

    def add_documents(self, documents: list[dict]) -> int:
        """
        Index a batch of documents.

        Args:
            documents: List of {"id": str, "text": str, "metadata": dict}
        Returns:
            Number of documents indexed.
        """
        ids = [doc["id"] for doc in documents]
        texts = [doc["text"] for doc in documents]
        metadatas = [doc.get("metadata", {}) for doc in documents]

        self.collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
        logger.info(f"[RAGEngine] Indexed {len(documents)} documents.")
        return len(documents)

    # ------------------------------------------------------------------
    # Retrieval + Generation
    # ------------------------------------------------------------------

    def query(self, question: str, filter_metadata: Optional[dict] = None) -> dict:
        """
        Retrieve relevant chunks and generate a grounded answer.

        Returns:
            {
              "answer": str,
              "sources": [{"id": str, "text": str, "score": float}],
              "tokens_used": int
            }
        """
        with tracer.start_as_current_span("rag.query") as span:
            span.set_attribute("rag.question", question[:200])
            span.set_attribute("rag.collection", self.collection_name)

            # Step 1: Retrieve
            results = self.collection.query(
                query_texts=[question],
                n_results=self.top_k,
                where=filter_metadata,
            )

            chunks = results["documents"][0]
            ids = results["ids"][0]
            distances = results["distances"][0]

            if not chunks:
                return {
                    "answer": "No relevant documents found in the knowledge base.",
                    "sources": [],
                    "tokens_used": 0,
                }

            span.set_attribute("rag.chunks_retrieved", len(chunks))

            # Step 2: Build grounded prompt
            context_block = "\n\n".join(
                f"[Source {ids[i]}] {chunks[i]}" for i in range(len(chunks))
            )
            user_prompt = f"""Context:\n{context_block}\n\nQuestion: {question}"""

            # Step 3: Generate
            messages = [
                SystemMessage(content=SYSTEM_PROMPT),
                HumanMessage(content=user_prompt),
            ]
            response = self.llm.invoke(messages)
            tokens = response.response_metadata.get("token_usage", {}).get("total_tokens", 0)

            sources = [
                {"id": ids[i], "text": chunks[i][:200] + "...", "score": 1 - distances[i]}
                for i in range(len(chunks))
            ]

            span.set_attribute("rag.tokens_used", tokens)

            return {
                "answer": response.content,
                "sources": sources,
                "tokens_used": tokens,
            }

    def similarity_search(self, query: str, top_k: Optional[int] = None) -> list[dict]:
        """Raw similarity search — returns chunks without generation."""
        k = top_k or self.top_k
        results = self.collection.query(query_texts=[query], n_results=k)
        return [
            {"id": results["ids"][0][i], "text": results["documents"][0][i]}
            for i in range(len(results["ids"][0]))
        ]
