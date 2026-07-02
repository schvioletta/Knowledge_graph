import os

from dotenv import load_dotenv
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import Qdrant
from qdrant_client import QdrantClient
from langchain_community.embeddings.gigachat import GigaChatEmbeddings
from langchain_community.chat_models.gigachat import GigaChat
from langchain.chains import RetrievalQA
from langchain_core.prompts import PromptTemplate


def load_pdf(path: str):
    loader = PyPDFLoader(path)
    return loader.load()


def split_docs(docs, chunk_size: int = 1000, chunk_overlap: int = 200):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    return splitter.split_documents(docs)


def get_qdrant_client() -> QdrantClient:
    url = os.getenv("QDRANT_URL", "http://localhost:6333")
    api_key = os.getenv("QDRANT_API_KEY") or None
    return QdrantClient(url=url, api_key=api_key)


def build_vector_store(
    docs,
    collection_name: str = "pdf_rag_collection",
):
    embeddings = GigaChatEmbeddings(
        credentials=os.getenv("GIGACHAT_API_KEY"),
        verify_ssl_certs=False,
    )

    # подключаемся к Qdrant по URL/API‑ключу напрямую
    vector_store = Qdrant.from_documents(
        docs,
        embeddings,
        url=os.getenv("QDRANT_URL", "http://localhost:6333"),
        api_key=os.getenv("QDRANT_API_KEY") or None,
        collection_name=collection_name,
    )
    return vector_store


def get_vector_store(collection_name: str = "pdf_rag_collection"):
    embeddings = GigaChatEmbeddings(
        credentials=os.getenv("GIGACHAT_API_KEY"),
        verify_ssl_certs=False,
    )
    client = get_qdrant_client()
    return Qdrant(
        client=client,
        collection_name=collection_name,
        embeddings=embeddings,
    )


def make_qa_chain(vector_store):
    llm = GigaChat(
        credentials=os.getenv("GIGACHAT_API_KEY"),
        model=os.getenv("GIGACHAT_MODEL", "GigaChat"),
        verify_ssl_certs=False,
        temperature=0,
    )
    # достаём побольше контекста
    retriever = vector_store.as_retriever(search_kwargs={"k": 10})

    # кастомный промпт, чтобы модель отвечала подробно и использовала весь контекст
    prompt_template = """
Ты — умный ассистент, который отвечает на вопросы по документу.
Тебе дан контекст (фрагменты документа) и вопрос пользователя.

Твоя задача:
- использовать максимум информации из контекста;
- дать развёрнутый, структурированный ответ;
- при необходимости делать краткое резюме всего соответствующего раздела, а не только одного абзаца;
- если каких‑то деталей нет в контексте, честно сказать об этом и не выдумывать.

КОНТЕКСТ:
{context}

ВОПРОС:
{question}

ДАЙ ПОДРОБНЫЙ ОТВЕТ НА РУССКОМ ЯЗЫКЕ:
"""

    prompt = PromptTemplate(
        template=prompt_template,
        input_variables=["context", "question"],
    )

    return RetrievalQA.from_chain_type(
        llm=llm,
        retriever=retriever,
        return_source_documents=True,
        chain_type_kwargs={"prompt": prompt},
    )


def ingest_pdf_to_qdrant(pdf_path: str, collection_name: str = "pdf_rag_collection"):
    docs = load_pdf(pdf_path)
    chunks = split_docs(docs)
    vector_store = build_vector_store(chunks, collection_name=collection_name)
    return vector_store


def interactive_rag(pdf_path: str, question: str):
    load_dotenv()

    collection_name = os.getenv("QDRANT_COLLECTION", "pdf_rag_collection")

    if os.getenv("REBUILD_COLLECTION", "true").lower() == "true":
        vector_store = ingest_pdf_to_qdrant(pdf_path, collection_name=collection_name)
    else:
        vector_store = get_vector_store(collection_name=collection_name)

    qa_chain = make_qa_chain(vector_store)
    result = qa_chain.invoke({"query": question})

    answer = result["result"]
    sources = result.get("source_documents", [])

    print("Ответ модели:\n")
    print(answer)
    print("\nИсточник(и):")
    for i, doc in enumerate(sources, start=1):
        print(f"{i}. {doc.metadata.get('source', 'unknown')} | стр. {doc.metadata.get('page', '?')}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="RAG по PDF с Qdrant и OpenAI")
    parser.add_argument("--pdf", required=True, help="Путь к PDF файлу")
    parser.add_argument("--question", required=True, help="Вопрос к содержимому PDF")
    args = parser.parse_args()

    interactive_rag(args.pdf, args.question)

