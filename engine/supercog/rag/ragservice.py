import asyncio
from fastapi import FastAPI, Depends, HTTPException, BackgroundTasks
from sqlmodel import SQLModel, Field, Session, create_engine, select, or_
from typing import List
import traceback
import uuid
import pandas as pd
import json
from collections import defaultdict

from supercog.shared.services import config, serve, db_connect
from supercog.engine.db import lifespan_manager, Agent, get_session, DocSourceConfig, DocIndex, DocSource
from supercog.engine.doc_source_factory import DocSourceFactory
from supercog.engine.run_context import RunContext, ContextInit

from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Document, StorageContext
from llama_index.vector_stores.postgres import PGVectorStore
import openai
from sqlalchemy import make_url, text

app = FastAPI(lifespan=lifespan_manager)
SERVICE = "ragservice"

# In-memory job storage (replace with a database in production)
indexing_jobs = {}

def make_index_name(index_id: str, prefix="idx_"):
    return prefix + index_id.replace("-", "_")

@app.get("/hello")
def hello(session: Session = Depends(get_session)):
    # Load the first agent
    agent = session.exec(select(Agent)).first()
    if agent:
        return {"message": "Hello World", "agent": str(agent)}
    else:
        return {"message": "agents table is empty"}

@app.post("/index/{index_id}/add_file")
async def add_file_to_index(index_id: str, file: str, session: Session = Depends(get_session)):
    # TODO: Implement adding a file to the specified DocIndex
    pass

@app.post("/index/{index_id}/attach_docsource")
async def start_indexing(
    index_id: str, 
    doc_source_config_id: str, 
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_session)
):
    doc_index = session.exec(select(DocIndex).where(DocIndex.id == index_id)).first()
    doc_source_config = session.exec(select(DocSourceConfig).where(DocSourceConfig.id == doc_source_config_id)).first()
    
    if not doc_index or not doc_source_config:
        raise HTTPException(status_code=404, detail="DocIndex or DocSourceConfig not found")

    doc_source = doc_source_config.doc_source
    secrets = doc_source.retrieve_secrets()

    run_context = RunContext(
        ContextInit(
            tenant_id = doc_source.tenant_id,
            user_id = doc_source.user_id,
            agent_id = None,
            agent_name = None,
            run_id = None,
            logs_channel = None,
            secrets = secrets, 
            enabled_tools = {},
            user_email = None,
            run_scope="private",
            doc_indexes=[],
        )
    )
    # Fetch and process documents
    docs_source: DocSourceFactory = DocSourceFactory.get_doc_factory(doc_source) 

    job_id = str(uuid.uuid4())
    indexing_jobs[job_id] = {"status": "started", "message": "Indexing job started"}

    background_tasks.add_task(index_documents, job_id, doc_index, doc_source_config, docs_source, run_context)

    return {"status": "Indexing started", "job_id": job_id}

async def index_documents(
        job_id: str, 
        doc_index: DocIndex, 
        doc_source_config: DocSourceConfig, 
        docs_source: DocSourceFactory,
        run_context: RunContext,
    ):
    await asyncio.sleep(1.0)
    print("Now indexing documents")
    with Session(db_connect("engine")) as session:
        try:
            # Initialize PostgreSQL vector store
            db_url = make_url(config.get_global("PGVECTOR_DB_URL"))
            openai.api_key = config.get_global("OPENAI_API_KEY")
            
            index_name = make_index_name(doc_index.id or "")
            vector_store = PGVectorStore.from_params(
                database=db_url.database,
                host=db_url.host,
                password=db_url.password,
                port=str(db_url.port or 5432),
                user=db_url.username,
                table_name=index_name,
                hybrid_search=True,
                embed_dim=1536,  # openai embedding dimension
                hnsw_kwargs={
                    "hnsw_m": 16,
                    "hnsw_ef_construction": 64,
                    "hnsw_ef_search": 40,
                    "hnsw_dist_method": "vector_cosine_ops",
                },
            )

            storage_context = StorageContext.from_defaults(vector_store=vector_store)

            # Initialize the document source
            docs_source.run_context = run_context
            docs_source.credentials = run_context.secrets
            documents = []
            folders = doc_source_config.folder_ids
            if len(folders) == 0:
                folders = [None]
            for folder in folders:
                async for doc in docs_source.get_documents(folder):
                    # Add the document to the index
                    documents.append(doc)

            # Create the index
            index = VectorStoreIndex.from_documents(
                documents,
                storage_context=storage_context,
                show_progress=True,
            )

            # Update the DocIndex status
            doc_index.status = "indexed"
            session.add(doc_index)
            session.commit()
            print("INDEXING DONE")

            indexing_jobs[job_id] = {"status": "completed", "message": f"Indexing completed for index {doc_index.id}"}

        except Exception as e:
            # Handle exceptions and update the DocIndex status
            traceback.print_exc()
            doc_index.status = "error"
            doc_index.error_message = str(e)
            session.add(doc_index)
            session.commit()
            indexing_jobs[job_id] = {"status": "error", "message": f"Error during indexing: {str(e)}"}

@app.get("/indexing_job/{job_id}")
async def get_indexing_job_status(job_id: str):
    if job_id not in indexing_jobs:
        raise HTTPException(status_code=404, detail="Indexing job not found")
    return indexing_jobs[job_id]

@app.get("/indexing_job/{job_id}/tail")
async def tail_indexing_job(job_id: str, session: Session = Depends(get_session)):
    # TODO: Implement tailing the log of an indexing job
    pass

@app.delete("/index/{index_id}/detach_docsource")
async def detach_docsource_from_index(
    index_id: str, 
    doc_id: str, 
    session: Session = Depends(get_session)
):
    try:
        # Initialize PostgreSQL vector store
        db_url = make_url(config.get_global("PGVECTOR_DB_URL"))
        index_name = make_index_name(index_id)
        vector_store = PGVectorStore.from_params(
            database=db_url.database,
            host=db_url.host,
            password=db_url.password,
            port=str(db_url.port or 5432),
            user=db_url.username,
            table_name=index_name,
            hybrid_search=True,
            embed_dim=1536,
            hnsw_kwargs={
                    "hnsw_m": 16,
                    "hnsw_ef_construction": 64,
                    "hnsw_ef_search": 40,
                    "hnsw_dist_method": "vector_cosine_ops",
                },
        )

        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)


        index.delete(doc_id)


        return {"message": f"Successfully detached doc_source {doc_id} from index {index_id}"}

    except Exception as e:
        raise RuntimeError(f"Error detaching doc_source from index {index_id}: {str(e)}")

@app.get("/index/{index_id}")
async def get_index_info(index_id: str, session: Session = Depends(get_session)):
    # TODO: Implement retrieving information about the specified DocIndex
    pass

@app.get("/index/{index_id}/query")
async def query_index(
    index_id: str, 
    query: str, 
    similarity_top_k: int = 1,
    session: Session = Depends(get_session)
):

    # Initialize PostgreSQL vector store
    db_url = make_url(config.get_global("PGVECTOR_DB_URL"))
    openai.api_key = config.get_global("OPENAI_API_KEY")
    
    index_name = make_index_name(index_id) #I assume index_id will be passed to endpoint
    vector_store = PGVectorStore.from_params(
        database=db_url.database,
        host=db_url.host,
        password=db_url.password,
        port=str(db_url.port or 5432),
        user=db_url.username,
        table_name=index_name,
        hybrid_search=True,
        embed_dim=1536,  # openai embedding dimension
        hnsw_kwargs={
            "hnsw_m": 16,
            "hnsw_ef_construction": 64,
            "hnsw_ef_search": 40,
            "hnsw_dist_method": "vector_cosine_ops",
        },
    )

    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    index = VectorStoreIndex.from_vector_store(vector_store, storage_context=storage_context)

    # Use hybrid search
    query_engine = index.as_query_engine(
        vector_store_query_mode="hybrid",
        similarity_top_k=similarity_top_k,
    )
    response = query_engine.query(query)

    return {
        "query": query,
        "response": str(response),
        "source_nodes": [
            {
                "text": node.node.text,
                "score": node.score,
                "metadata": node.node.metadata
            } for node in response.source_nodes
        ]
    }

@app.get("/index/{index_id}/metadata")
async def list_index_metadata(
    index_id: str,
    limit: int = 100,
    offset: int = 0,
    session: Session = Depends(get_session)
):

    # Initialize PostgreSQL connection
    db_url = make_url(config.get_global("PGVECTOR_DB_URL"))
    index_name = make_index_name(index_id, prefix="data_idx_") #It seems llamaindex adds "data_" in front of table name

    # Connect to the database
    engine = create_engine(db_url)
    with engine.connect() as connection:
        # Query to fetch metadata
        query = text(f"""
            SELECT DISTINCT ON (metadata_->>'file_name') metadata_
            FROM {index_name}
            ORDER BY metadata_->>'file_name', id
            LIMIT :limit OFFSET :offset
        """)
        
        result = connection.execute(query, {"limit": limit, "offset": offset})
        rows = result.fetchall()

    # Process the results
    metadata_summary = []
    for row in rows:
        metadata = row[0]
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        summary = {
            'file_name': metadata.get('file_name'),
            'file_path': metadata.get('file_path'),
            'file_type': metadata.get('file_type'),
            'file_size': metadata.get('file_size'),
            'creation_date': metadata.get('creation_date'),
            'last_modified_date': metadata.get('last_modified_date')
        }
        metadata_summary.append(summary)

    # Get total count of unique files
    with engine.connect() as connection:
        count_query = text(f"""
            SELECT COUNT(DISTINCT metadata_->>'file_name') as count
            FROM {index_name}
        """)
        total_documents = connection.execute(count_query).scalar()

    return {
        "index_id": index_id,
        "total_documents": total_documents,
        "metadata": metadata_summary
    }

if __name__ == "__main__":
    try:
        serve(app, SERVICE)
    except KeyboardInterrupt:
        print("Shutting down")
