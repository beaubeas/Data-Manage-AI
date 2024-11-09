# Docstore service

We will implement a generic document store (probably just a Postgres db storing pointers to files
on S3). The store will support storing files of any type, and annotating files with metadata.
It will also support file versioning, where new versions of a file may be in a different format,
and maintain backlinks to their prior version.

We will support crawling in the Docstore, for automated ingestion of a large number of documents.
This works by creating a `crawler` instance with configuration about where to retrieve the set
of documents. When a crawler is active it looks for (new) documents and adds them to the docstore,
potentially vector-indexing them at the same time.

The Docstore will also support storing vectors and vector search (via pg_vector). To use this
you create a vector store object, add documents to it, and then perform searches against the
store. 

## Docstore API

    ## files
    POST /tenant/<tenant_id>/files
    {content: ..., content_url: ..., metadata, owner_id, vectorstore: ...}
    Stores a new file. You can pass the `vectorstore` parameter as
    a JSON dict of the arguments you would pass to PATCH...<vectorstore_id> to add the file to a store.
    A hash is calculated for every file, and we won't store a file twice with the same
    hash. This ensures that duplicates are not stored and makes it safe to call this
    endpoint multiple times.
    <-- returns the {file_id:, file_hash: ..., name:, path:, mime_type:}

    DELETE /tenant/<tenant_id>/files/<file_id>
    Deletes a file.

    POST /tenant/<tenant_id>/files/<file_id>
    {type: ..., content: ..., content_url: ..., metadata, owner_id}
    Creates a new version of file, possibly converting format.

    LIST /tenant/<tenant_id>/files
    {filter: ...}

    ## embedding models
    GET /embedmodels
    Returns the list of available embedding model descriptors.

    POST /tenant/<tenant_id>/embedmodels
    {config...}
    Registers a (non-builtin) embedding model for a tenant.
    <-- returns the embedmodel_id

    GET /tenant/<tenant_id>/embedmodels
    <-- returns the list of embedding models for the tenant

    DELETE /tenant/<tenant_id>/embedmodels/<embedmodel_id>

    ## vector stores
    POST /tenant/<tenant_id>/vectorstores
    {name: ..., owner_id: ..., embedmodel_id: ...}
    Creates a vectorstore. You must have created an embedding under the
    tenatnt and pass its ID. Owner ID is optional for Team-shared stores.
    <-- returns the vectorstore_id

    DELETE /tenant/<tenant_id>/vectorstores/<vectorstore_id>
    Deletes a vector store.

    PATCH /tenant/<tenant_id>/vectorstores/<vectorstore_id>
    {file_id: ..., chunk_size: ..., }
    Adds a document to a vectorstore.

    GET /tenant/<tenant_id>/vectorstores/<vectorstore_id>
    {start..., count...}
    Lists the objects in the vectorstore. Uses paging.

    POST /tenant/<tenant_id>/vectorstores/<vectorstore_id>/search
    {query...:, k_docs:...}
    Queries the store and returns a set of matching docs.

    ## crawlers
    POST /tenant/<tenant_id/>/crawlers
    {data_source:... , owner_id: ..., active: bool, vectorstore_id}
    The vectorstore_id is optional.

    GET /tenant/<tenant_id/>/crawlers
    <-- returns the list of crawlers for a tenant

    PATCH /tenant/<tenant_id/>/crawlers/<crawler_id>
    <...modify a crawler.., including setting active=false>

    DELETE /tenant/<tenant_id/>/crawlers/<crawler_id>
