from langchain_openai import OpenAIEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import CharacterTextSplitter
from langchain_openai import OpenAI
from langchain.chains import RetrievalQA
import chromadb
import pandas as pd
import os
import dotenv

# Load environment variables from .env file
dotenv.load_dotenv("/Users/scottp/envs/local.env")

def load_documents_from_csv(csv_path, text_column):
    """
    Load documents from a CSV file
    Args:
        csv_path: Path to the CSV file
        text_column: Name of the column containing the text to be indexed
    Returns:
        List of texts
    """
    try:
        df = pd.read_csv(csv_path)
        if text_column not in df.columns:
            raise ValueError(f"Column '{text_column}' not found in CSV file")
        
        # Remove any NaN values and convert to list
        texts = df[text_column].dropna().tolist()
        print(f"Loaded {len(texts)} documents from CSV")
        return texts
    
    except Exception as e:
        print(f"Error loading CSV file: {str(e)}")
        return []

def create_and_persist_vectorstore(texts, persist_directory="./chroma_db"):
    """
    Create and persist a Chroma vector store from a list of texts
    """
    if not texts:
        raise ValueError("No texts provided for indexing")
        
    # Initialize the embedding model
    embeddings = OpenAIEmbeddings()
    
    # Create text splitter for longer texts
    text_splitter = CharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200
    )
    
    # Split texts into chunks if they're long
    documents = text_splitter.create_documents(texts)
    
    client = chromadb.PersistentClient()
    # Create and persist the vector store
    if os.path.exists("./chroma_db"):
        print("Loading existing vector store")
        vectorstore = Chroma(
            embedding_function=embeddings,
            persist_directory=persist_directory,
            collection_name='v_db'
        )
    else:        
        vectorstore = Chroma.from_documents(
            documents=documents,
            embedding=embeddings,
            persist_directory=persist_directory,
            collection_name='v_db'
        )
        # Persist the vector store to disk
        print(f"Vector store persisted to {persist_directory}")   
    
    return vectorstore

def load_vectorstore(persist_directory="./chroma_db"):
    """
    Load a previously persisted Chroma vector store
    """
    embeddings = OpenAIEmbeddings()
    vectorstore = Chroma(
        persist_directory=persist_directory,
        embedding_function=embeddings
    )
    return vectorstore

def query_vectorstore(query, vectorstore, k=2):
    """
    Query the vector store for similar documents
    """
    # Perform similarity search
    docs = vectorstore.similarity_search(query, k=k)
    return docs

# Example usage
if __name__ == "__main__":
    # Example CSV structure:
    # | text_content                | metadata (optional) |
    # |-----------------------------|--------------------|
    # | "Document text here"        | Some metadata      |
    
    # Load documents from CSV
    csv_path = "tools.csv"  # Replace with your CSV file path
    text_column = "name"  # Replace with your text column name
    
    texts = load_documents_from_csv(csv_path, text_column)
    
    if texts:
        # Create and persist the vector store
        loaded_vectorstore = create_and_persist_vectorstore(texts)
        
        # Load the persisted vector store
        #loaded_vectorstore = load_vectorstore()
        
        # Example query
        query = "query users from the dashboard database"
        results = query_vectorstore(query, loaded_vectorstore)
        
        # Print results
        print("\nQuery:", query)
        print("\nRelevant documents:")
        breakpoint()
        for i, doc in enumerate(results, 1):
            print(f"\n{i}. {doc}")


## FAISS implementation

# import numpy as np
# from rank_bm25 import BM25Okapi
# from sentence_transformers import SentenceTransformer
# import faiss
# import pandas as pd
# from openai import OpenAI
# import os

# class HybridSearch:
#     def __init__(self, documents):
#         self.documents = documents

#         # BM25 initialization
#         tokenized_corpus = [doc.split(" ") for doc in documents]
#         self.bm25 = BM25Okapi(tokenized_corpus)

#         # Sentence transformer for embeddings
#         self.model = SentenceTransformer('paraphrase-MiniLM-L6-v2')
#         self.document_embeddings = self.model.encode(documents)
        
#         # FAISS initialization
#         self.index = faiss.IndexFlatL2(self.document_embeddings.shape[1])
#         self.index.add(np.array(self.document_embeddings).astype('float32'))

#     def search(self, query, top_n=10):
#         # BM25 search
#         bm25_scores = self.bm25.get_scores(query.split(" "))
#         top_docs_indices = np.argsort(bm25_scores)[-top_n:]
        
#         # Get embeddings of top documents from BM25 search
#         top_docs_embeddings = [self.document_embeddings[i] for i in top_docs_indices]
#         query_embedding = self.model.encode([query])

#         # FAISS search on the top documents
#         sub_index = faiss.IndexFlatL2(top_docs_embeddings[0].shape[0])
#         sub_index.add(np.array(top_docs_embeddings).astype('float32'))
#         _, sub_dense_ranked_indices = sub_index.search(np.array(query_embedding).astype('float32'), top_n)

#         # Map FAISS results back to original document indices
#         final_ranked_indices = [top_docs_indices[i] for i in sub_dense_ranked_indices[0]]

#         # Retrieve the actual documents
#         ranked_docs = [self.documents[i] for i in final_ranked_indices]

#         return ranked_docs

# client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

# def llm_search(query, tools):
#         SEARCH_PROMPT = (
#             f"Given the list of tools below, return one or two suggestions for the tool that best fits: {query}.\n" +
#             "Only return the exact names of the tool, comma separated, or NONE if no tool fits the purpose.\n" +
#             "----------" +
#             "\n".join(tools)
#         )
#         messages = [
#             {"role": "system", "content": ""},
#             {"role": "user", "content": SEARCH_PROMPT}
#         ]

#         response = client.chat.completions.create(
#             model="gpt-4o-mini",
#             messages=messages,
#             response_format={ "type": "text" },
#         )
#         result = response.choices[0].message.content
#         return result

# df = pd.read_csv("./tools.csv")
# #texts = df["name"].dropna().tolist()
# texts = [f"{row['name']} ({row['help']})" for row in df.to_dict('records')]
# tools = texts

# hs = HybridSearch(texts)
# queries = [
#     "query users from the dashboard database",
#     "web research",
#     "get the text from this image",
#     "analyze this image",
#     "send a message to this slack channel",
#     "what is in this pdf file",
# ]
# for query in queries:
#     print("\nQuery:", query)
#     results = hs.search(query, top_n=10)
#     print(results)
#     lres = llm_search(query, tools)
#     print("----")
#     print(lres)
#     print("----")
