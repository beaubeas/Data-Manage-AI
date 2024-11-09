import os
import re
from typing import Any, Callable
from io import StringIO
from contextlib import contextmanager

from openai import OpenAI

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
from supercog.shared.utils import sanitize_string
from supercog.shared.services import config

import duckdb
import pandas as pd
import numpy as np

class DuckdbTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="duckdb_tool",
            system_name="DuckDB",
            logo_url=self.logo_from_domain("duckdb.org"),
            auth_config={
                "strategy_token": {
                    "database_file": "Database file name with path",
                },
            },
            category=ToolCategory.CATEGORY_FILES,
            help="""
Use DuckDB to load and store tabular data, and manipulate it with SQL.
"""
        )

    def get_tools(self) -> list[Callable]:
        """Returns a list of callable methods for the DuckDB tool."""
        return self.wrap_tool_functions([
            self.read_file_as_dataframe,
            self.add_column_to_dataframe,
            self.write_dataframe_to_file,
            self.convert_text_to_dataframe,
            self.query_dataframe,
            self.save_duckdb_table,
            self.load_duckdb_table,
            self.alter_duckdb_table,
            self.query_duckdb_tables,
            self.list_duckdb_tables,
            self.delete_duckdb_table,
        ])

    def test_credential(self, cred, secrets: dict) -> str:
        """Tests the provided credentials by attempting to connect to the database."""
        if 'database_file' in secrets:
            try:
                con = duckdb.connect(secrets["database_file"])
                con.execute("SELECT 1")
                con.close()
            except Exception as e:
                return f"Error: {e}"
        else:
            return None

    def _infer_format_from_name(self, file_name: str) -> str:
        """Infers the file format from the file name."""
        if file_name.endswith(".csv"):
            return "csv"
        elif file_name.endswith(".parquet"):
            return "parquet"
        elif file_name.endswith(".xlsx"):
            return "excel"
        else:
            raise RuntimeError(f"Can't infer format from file name '{file_name}'")

    def _get_db_file(self):
        """Returns the database file path from credentials or a default value."""
        if 'database_file' in self.credentials:
            return self.credentials['database_file']
        else:
            return "duckdb.db"

    @contextmanager
    def duckdb_connection(self):
        """Context manager for handling DuckDB connections."""
        con = duckdb.connect(self._get_db_file())
        try:
            yield con
        finally:
            con.close()

    def read_file_as_dataframe(
        self,
        file_uri: str,
        file_format: str = "infer",
        skip_rows: int = 0,
        cleanup_col_names: bool = True,
    ) -> dict:
        """ Reads the indicated file (or URL) and returns the contents as a DataFrame preview.
            File format should be "infer", "csv", "parquet", "json", "excel". Set
            'ignore_rows' to a positive number if you want to ignore rows at the
            top of the file.
        """
        if not file_uri.startswith("http") and not os.path.exists(file_uri):
            return f"Error: file not found '{file_uri}'"
        
        if file_format == "infer":
            file_format = self._infer_format_from_name(file_uri)

        with self.duckdb_connection() as con:
            if file_format == "csv":
                sql = f"SELECT * FROM read_csv('{file_uri}');"
                print("SQL: ", sql)
                df = con.execute(sql).df()
            elif file_format == "parquet":
                sql = f"SELECT * FROM read_parquet('{file_uri}');"
                print("SQL: ", sql)
                df = con.execute(sql).df()
            elif file_format == "json":
                df = con.execute(f"SELECT * FROM read_json('{file_uri}');").df()
            elif file_format == "excel":
                df = pd.read_excel(file_uri, skiprows=skip_rows)
            else:
                return {"status": "error", "message": "File format not recognized"}

        if cleanup_col_names:
            df.columns = (
                df.columns.str.strip().str.lower().str.replace(r'\W+', '_', regex=True).str.replace(r'_$', '', regex=True)
            )
        
        return self.get_dataframe_preview(df, name_hint=file_uri)

    def convert_text_to_dataframe(
            self,
            text: str,
            format: str = "csv",
            name_hint: str = "text1",
    ):
        """ Converts the indicated text to a DataFrame. Format can be "csv" or "json". """
        if format == "csv":
            df = pd.read_csv(StringIO(text))
        elif format == "json":
            df = pd.read_json(StringIO(text))
        else:
            return {"status": "error", "message": f"Format '{format}' not recognized"}

        return self.get_dataframe_preview(df, name_hint=name_hint, sanitize_column_names=False)
    
    def add_column_to_dataframe(
        self,
        dataframe_var: str,
        column_name: str,
        column_data: list[str],
    ) -> dict:
        """ Adds a column to the indicated DataFrame. Return a success message."""
        df, df_name = self.get_dataframe_from_handle(dataframe_var)

        if len(column_data) == 1:
            df[column_name] = column_data[0]
            return {"status": "success", "message":"The singular value was applied to all rows"}
        elif len(column_data) < df.shape[0]:
            num_repetitions = -(-len(df) // len(column_data))
            repeated_values = np.tile(column_data, num_repetitions)[:len(df)]
            df[column_name] = repeated_values
            return {"status": "success", "message":"Values were repeated to fill all rows"}
        else:
            df[column_name] = column_data[:len(df)]
            return {"status": "success", "dataframe":df_name}

    def write_dataframe_to_file(
        self,
        dataframe_var: str,
        file_name,
        file_format="infer",
    ) -> str:
        """ Writes the indicated DataFrame to the indicated file. File_format
            can be one of: "infer", "csv", "parquet", or "excel".
        """
        supercog_df, df_name = self.get_dataframe_from_handle(dataframe_var)
        duckdb.register('supercog_df', supercog_df)

        if file_format == "infer":
            file_format = self._infer_format_from_name(file_name)

        if file_format == "csv":
            duckdb.sql("SELECT * from supercog_df").write_csv(file_name)
            mime_type = "text/csv"
        elif file_format == "parquet":
            duckdb.sql("SELECT * from supercog_df").write_parquet(file_name)
            mime_type = "application/parquet"
        elif file_format == "excel":
            supercog_df.to_excel(file_name, index=False)
            mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        else:
            return {"status": "error", "message": f"File format '{file_format}' not recognized"}

        download_url = self.run_context.upload_user_file_to_s3(
            file_name=file_name,
            mime_type=mime_type,
            return_download_url=True,
        )
        return "File saved, download link: " + download_url.get("url", "")

    def save_duckdb_table(
            self,
            dataframe_var: str,
            table_name: str,
            force_overwrite: bool=False,
    ) -> str:
        """ Stores the data from the indicated dataframe to a duckdb table with the given name. 
            Will replace any existing table if 'force_overwrite' is True.
        """
        df, df_name = self.get_dataframe_from_handle(dataframe_var)
        with self.duckdb_connection() as con:
            name = sanitize_string(table_name)
            if force_overwrite:
                con.execute(f"DROP TABLE IF EXISTS {name}")
            con.execute(f"CREATE TABLE {name} AS SELECT * FROM df")

        return f"Saved table: '{name}'"

    def load_duckdb_table(
            self,
            table_name: str,
            preview_rows: int = 20,
            max_rows: int|None = None,
            preserve_case: bool = False,
    ) -> dict:
        """ Reads the indicated table from the Duckdb database and returns it as a DataFrame. 
            Will return 'preview_rows' number of rows in the preview. Pass preserve_case=True
            to keep the original column names. Pass 'max_rows' to limit the total number
            of rows returned.
        """
        with self.duckdb_connection() as con:
            try:
                if max_rows:
                    limit = f" LIMIT {max_rows}"
                else:
                    limit = ""
                df = con.execute(f"SELECT * FROM {table_name}{limit}").df()
                return self.get_dataframe_preview(
                    df, 
                    name_hint=table_name, 
                    max_rows=preview_rows,
                    sanitize_column_names=not preserve_case)
            except duckdb.CatalogException:
                return {
                    "status": "error", 
                    "message": f"Table '{table_name}' not found in db file {self._get_db_file()}"
                }

    def alter_duckdb_table(
            self,
            sql_statement: str,
    ) -> dict:
        """ Executes the given SQL "alter table" statement to modify a Duckdb table.
        """
        with self.duckdb_connection() as con:
            df = con.execute(sql_statement).df()
            return self.get_dataframe_preview(df)

    def query_duckdb_tables(
            self,
            sql_query: str,
            name_hint: str = "query_result",
    ) -> dict:
        """ Executes the given SQL query on the Duckdb database. ALWAYS DOUBLE QUOTE 
            COLUMN REFERENCES IN THE SQL QUERY. Returns the results as a dataframe.
        """
        with self.duckdb_connection() as con:
            if m := re.match("create view (\w+) ", sql_query, re.IGNORECASE):
                view_name = m.group(1)
                con.execute(f"DROP VIEW IF EXISTS {view_name};")

            df = con.execute(sql_query).df()
            return self.get_dataframe_preview(df, name_hint=name_hint)

    def list_duckdb_tables(self) -> str:
        """ Returns the names of the tables stored in the DuckDB database. """
        with self.duckdb_connection() as con:
            df = con.execute("SHOW TABLES").df()
            return str(df)
        
    def _get_table_list(self) -> pd.DataFrame:
        """ Returns the names of the tables stored in the DuckDB database. """
        with self.duckdb_connection() as con:
            return con.execute("SHOW TABLES").df()

    def _query_table(self, table_name: str) -> pd.DataFrame:
        """ Returns the contents of the indicated table from the DuckDB database. """
        with self.duckdb_connection() as con:
            return con.execute(f"SELECT * FROM {table_name}").df()
    
    def delete_duckdb_table(self, table_name: str) -> str:
        """ Deletes the indicated table from the DuckDB database."""
        with self.duckdb_connection() as con:
            try:
                con.execute(f"DROP TABLE {table_name}")
            except duckdb.CatalogException:
                con.execute(f"DROP VIEW {table_name}")
        
        return "success"

    async def query_dataframe(
            self, 
            dataframe_var: str, 
            query: str, 
            result_name: str|None=None,
            callbacks: Any=None) -> dict:
        """ Query the indicated DataFrame with the indicated Duckdb-syntax SQL query. 
            Remember to use single quotes to quote column names.
            Returns a new dataframe, and uses 'result_name' as the variable name if provided.
        """
        df, df_name = self.get_dataframe_from_handle(dataframe_var)
        globals()[df_name] = df
        await self.log(f"Querying DataFrame {df_name} with query: '{query}'", callbacks=callbacks)
        result = duckdb.sql(query)
        df = result.df()
        return self.get_dataframe_preview(df, name_hint=result_name or df_name, sanitize_column_names=False)
    
    def llm_enrich_column(
            self, 
            dataframe_var: str, 
            source_column: str, 
            result_column: str, 
            prompt: str,
            llm_model: str = "gpt-3.5-turbo-0125",
            callbacks: LangChainCallback=None) -> dict:
        """ Uses an LLM to create a new column in the dataframe by creating a completion using the 
            prompt and the source_column value for each row. Returns a new dataframe with the
            additional column added. 
        """
        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))

        with self.duckdb_connection() as con:
            df, df_name = self.get_dataframe_from_handle(dataframe_var)

            def llm_enricher(target_val: str) -> str:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": f"{prompt}: {target_val}"}
                ]
                print("Running LLM enricher with messages: ", messages)
                response = client.chat.completions.create(
                    model=llm_model,
                    messages=messages,
                )
                if hasattr(response, 'choices') and len(response.choices) > 0:
                    result = response.choices[0].message.content or ""
                    print(f"Result: {result}", callbacks)
                else:
                    result = "LLM result missing"
                return result
            
            con.create_function("llm_enricher", llm_enricher)
            
            globals()[df_name] = df
            result = con.execute(f"SELECT *, llm_enricher({source_column}) AS {result_column} FROM {df_name}")
            df = result.df()

        return self.get_dataframe_preview(df, name_hint=dataframe_var)



###### ASYNCIO VERSION

# -------------------------------

# import asyncio
# import aioduckdb 
# import os
# import re
# from typing   import Any, Callable
# from io import StringIO
# from concurrent.futures import ThreadPoolExecutor
# from contextlib import asynccontextmanager



# from openai import OpenAI

# from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
# from supercog.shared.utils import sanitize_string
# from supercog.shared.services import config


# import duckdb
# import pandas as pd
# import numpy as np

# class DuckdbTool(ToolFactory):
#     def __init__(self):
#         super().__init__(
#             id = "duckdb_tool",
#             system_name = "DuckDB",
#             logo_url=self.logo_from_domain("duckdb.org"),
#             auth_config = {
#                 "strategy_token": {
#                     "database_file": "Database file name with path",
#                 },

#             },
#             category=ToolCategory.CATEGORY_FILES,
#             help="""
#     Use DuckDB to load and store tabular data, and manipulate it with SQL.
# """
#         )
#     def get_tools(self) -> list[Callable]:
#         return self.wrap_tool_functions([
#             self.read_file_as_dataframe,
#             self.add_column_to_dataframe,
#             #self.get_dataframe_as_text,
#             self.write_dataframe_to_file,
#             self.convert_text_to_dataframe,
#             self.query_dataframe,
#             self.save_duckdb_table,
#             self.load_duckdb_table,
#             self.alter_duckdb_table,
#             self.query_duckdb_tables,
#             self.list_duckdb_tables,
#             self.delete_duckdb_table,
#             #self.llm_enrich_column,
#         ])

#     async def test_credential(self, cred, secrets: dict) -> str:
#         if 'database_file' in secrets:
#             try:
#                 con = await aioduckdb.connect(secrets["database_file"]) 
#                 await con.execute("select 1")
#             except Exception as e:
#                 return f"Error: {e}"
#         else:
#             return None

#     def _infer_format_from_name(self, file_name: str) -> str:
#         if file_name.endswith(".csv"):
#             return "csv"
#         elif file_name.endswith(".parquet"):
#             return "parquet"
#         elif file_name.endswith(".xlsx"):
#             return "excel"
#         else:
#             raise RuntimeError(f"Can't infer format from file name '{file_name}'")

#     def _get_db_file(self):
#         if 'database_file' in self.credentials:
#             return self.credentials['database_file']
#         else:
#             return "duckdb.db"

#     @asynccontextmanager
#     async def async_duckdb(self):
#         con = await aioduckdb.connect(self._get_db_file())
#         yield con

#     async def read_csv_async(self, url, connection: duckdb.DuckDBPyConnection):
#         loop = asyncio.get_running_loop()
#         with ThreadPoolExecutor() as pool:
#             return await loop.run_in_executor(pool, connection.read_csv, url)

#     async def read_file_as_dataframe(
#         self,
#         file_uri: str,
#         file_format:str="infer",
#         skip_rows:int=0,
#         cleanup_col_names: bool = True,
#     ) -> dict:
#         """ Reads the indicated file (or URL) and returns the contents as a DataFrame preview.
#             File format should be "infer", "csv", "parquet", "json", "excel". Set
#             'ignore_rows' to a positive number if you want to ignore rows at the
#             top of the file.
#         """
#         if not file_uri.startswith("http") and not os.path.exists(file_uri):
#             return f"Error: file not found '{file_uri}'"
        
#         if file_format == "infer":
#             file_format = self._infer_format_from_name(file_uri)

#         async with self.async_duckdb() as con:
#             if file_format == "csv":
#                 sql = f"SELECT * FROM read_csv('{file_uri}');"
#                 print("SQL: ", sql)
#                 cursor = await con.execute(sql)
#                 df = await cursor.df() 
#             elif file_format == "parquet":
#                 sql = f"SELECT * FROM read_parquet('{file_uri}');"
#                 print("SQL: ", sql)
#                 cursor = await con.execute(sql)
#                 df = await cursor.df() 
#             elif file_format == "json":
#                 cursor = await con.execute(f"SELECT * FROM read_json('{file_uri}');")
#                 df = await cursor.df() 
#             elif file_format == "excel":
#                 df = pd.read_excel(file_uri, skiprows=skip_rows)

#         if cleanup_col_names:
#             # Strip whitespace, lowercase, replace special characters, remove trailing underscore
#             df.columns = (
#                 df.columns.str.strip().str.lower().str.replace(r'\W+', '_', regex=True).str.replace(r'_$','', regex=True)
#             )

#         else:
#             return {"status": "error", "message": "File format not recognized"}    
        
#         return self.get_dataframe_preview(df, name_hint=file_uri)

#     def convert_text_to_dataframe(
#             self,
#             text: str,
#             format: str = "csv",
#             name_hint: str = "text1",
#     ):
#         """ Converts the indicated text to a DataFrame. Format can be "csv" or "json". """
#         if format == "csv":
#             df = pd.read_csv(StringIO(text))
#         elif format == "json":
#             df = pd.read_json(StringIO(text))
#         else:
#             return {"status": "error", "message": f"Format '{format}' not recognized"}

#         return self.get_dataframe_preview(df, name_hint=name_hint, sanitize_column_names=False)
    
#     def add_column_to_dataframe(
#         self,
#         dataframe_var: str,
#         column_name: str,
#         column_data: list[str],
#     ) -> dict:
#         """ Adds a column to the indicated DataFrame. Return a success message."""
#         df, df_name = self.get_dataframe_from_handle(dataframe_var)

#         if len(column_data) == 1:
#             df[column_name] = column_data[0]
#             return {"status": "success", "message":"The singular value was applied to all rows"}
#         elif len(column_data) < df.shape[0]:
#             num_repetitions = -(-len(df) // len(column_data))
#             repeated_values = np.tile(column_data, num_repetitions)[:len(df)]
#             df[column_name] = repeated_values
#             return {"status": "success", "message":"Values were repeated to fill all rows"}
#         else:
#             df[column_name] = column_data[:len(df)]
#             return {"status": "success", "dataframe":df_name}
    
#     def get_dataframe_as_text(
#         self,
#         dataframe_var: str,
#         start_row: int = 0,
#         total_rows: int|None=None,
#     ) -> str:
#         """ Returns the contents of the indicated DataFrame as a string. You can limit
#             the rows returned using start_row and total_rows parameters. """
#         df, _ = self.get_dataframe_from_handle(dataframe_var)
#         if total_rows is not None:
#             df = df.iloc[start_row:start_row+total_rows]
#         elif start_row > 0:
#             df = df.iloc[start_row:]
#         return df.to_string(index=False)
    
#     def write_dataframe_to_file(
#         self,
#         dataframe_var: str,
#         file_name,
#         file_format="infer",
#     ) -> dict:
#         """ Writes the indicated DataFrame to the indicated file. File_format
#             can be one of: "infer", "csv", "parquet", or "excel".
#         """
#         supercog_df, df_name = self.get_dataframe_from_handle(dataframe_var)
#         duckdb.register('supercog_df', supercog_df)

#         if file_format == "infer":
#             file_format = self._infer_format_from_name(file_name)

#         if file_format == "csv":
#             duckdb.sql("SELECT * from supercog_df").write_csv(file_name)
#         elif file_format == "parquet":
#             duckdb.sql("SELECT * from supercog_df").write_parquet(file_name)
#         elif file_format == "excel":
#             supercog_df.to_excel(file_name, index=False)
#         else:
#             return {"status": "error", "message": f"File format '{file_format}' not recognized"}

#         return {"status":"success"}

#     def save_duckdb_table(
#             self,
#             dataframe_var: str,
#             table_name: str,
#             force_overwrite: bool=False,
#     ) -> str:
#         """ Stores the data from the indicated dataframe to a duckdb table with the given name. 
#             Will replace any existing table if 'force_overwrite' is True.
#         """
#         df, df_name = self.get_dataframe_from_handle(dataframe_var)
#         con = duckdb.connect(self._get_db_file())

#         name = sanitize_string(table_name)
#         if force_overwrite:
#             con.execute(f"drop table if exists {name}")
#         con.execute(f"create table {name} as select * from df")

#         return f"Saved table: '{name}'"

#     async def load_duckdb_table(
#             self,
#             table_name: str,
#             preview_rows: int = 20,
#             max_rows: int|None = None,
#             preserve_case: bool = False,
#     ) -> dict:
#         """ Reads the indicated table from the Duckdb database and returns it as a DataFrame. 
#             Will return 'preview_rows' number of rows in the preview. Pass preserve_case=True
#             to keep the original column names. Pass 'max_rows' to limit the total number
#             of rows returned.
#         """

#         async with self.async_duckdb() as con:
#             try:
#                 if max_rows:
#                     limit = f" LIMIT {max_rows}"
#                 else:
#                     limit = ""
#                 cursor = await con.execute(f"select * from {table_name} {limit}")
#                 df = await cursor.df()
#                 return self.get_dataframe_preview(
#                     df, 
#                     name_hint=table_name, 
#                     max_rows=preview_rows,
#                     sanitize_column_names=not preserve_case)
#             except duckdb.duckdb.CatalogException:
#                 return {
#                     "status": "error", 
#                     "message": f"Table '{table_name}' not found in db file {self._get_db_file()}"
#                 }

#     async def alter_duckdb_table(
#             self,
#             sql_statement: str,
#     ) -> dict:
#         """ Executes the given SQL "alter table" statement to modify a Duckdb table.
#         """
#         async with self.async_duckdb() as con:
#             cursor = await con.execute(sql_statement)
#             df = await cursor.df()

#             return self.get_dataframe_preview(df)

#     async def query_duckdb_tables(
#             self,
#             sql_query: str,
#             name_hint: str = "query_result",
#     ) -> dict:
#         """ Executes the given SQL query on the Duckdb database. ALWAYS DOUBLE QUOTE 
#             COLUMN REFERENCES IN THE SQL QUERY. Returns the results as a dataframe.
#         """
#         async with self.async_duckdb() as con:
#             if m := re.match("create view (\w+) ", sql_query, re.IGNORECASE):
#                 view_name = m.group(1)
#                 await con.execute(f"DROP VIEW IF EXISTS {view_name};")

#             cursor = await con.execute(sql_query)
#             df = await cursor.df()
#             return self.get_dataframe_preview(df, name_hint=name_hint)

#     async def list_duckdb_tables(self) -> str:
#         """ Returns the names of the tables stored in the DuckDB database. """
#         async with self.async_duckdb() as con:
#             cursor = await con.execute("SHOW TABLES")
#             df = await cursor.df()
#             return str(df)
        
#     async def _get_table_list(self) -> pd.DataFrame:
#         """ Returns the names of the tables stored in the DuckDB database. """
#         async with self.async_duckdb() as con:
#             cursor = await con.execute("SHOW TABLES")
#             df = await cursor.df()
#             return df

#     async def _query_table(self, table_name: str) -> pd.DataFrame:
#         """ Returns the contents of the indicated table from the DuckDB database. """
#         async with self.async_duckdb() as con:
#             cursor = await con.execute(f"SELECT * FROM {table_name}")
#             df = await cursor.df()
#             return df
    
#     async def delete_duckdb_table(self, table_name: str) -> str:
#         """ Deletes the indicated table from the DuckDB database."""
#         async with self.async_duckdb() as con:
#             try:
#                 await con.execute(f"DROP TABLE {table_name}")
#             except duckdb.duckdb.CatalogException:
#                 await con.execute(f"DROP VIEW {table_name}")
        
#         return "success"
    

#     async def query_dataframe(
#             self, 
#             dataframe_var: str, 
#             query: str, 
#             result_name: str|None=None,
#             callbacks: Any=None) -> dict:
#         """ Query the indicated DataFrame with the indicated Duckdb-syntax SQL query. 
#             Remember to use single quotes to quote column names.
#             Returns a new dataframe, and uses 'result_name' as the variable name if provided.
#         """
#         df, df_name = self.get_dataframe_from_handle(dataframe_var)
#         globals()[df_name] = df
#         await self.log(f"Querying DataFrame {df_name} with query: '{query}'", callbacks=callbacks)
#         result = duckdb.sql(query)
#         df = result.df()
#         return self.get_dataframe_preview(df, name_hint=result_name or df_name, sanitize_column_names=False)
    
#     async def llm_enrich_column(
#             self, 
#             dataframe_var: str, 
#             source_column: str, 
#             result_column: str, 
#             prompt: str,
#             llm_model: str = "gpt-3.5-turbo-0125",
#             callbacks: LangChainCallback=None) -> dict:
#         """ Uses an LLM to create a new column in the dataframe by creating a completion using the 
#             prompt and the source_column value for each row. Returns a new dataframe with the
#             additional column added. 
#         """
#         client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))

#         con = duckdb.connect(self._get_db_file())
#         df, df_name = self.get_dataframe_from_handle(dataframe_var)

#         def llm_enricher(target_val: str) -> str:
#             messages = [
#                 {"role": "system", "content": "You are a helpful assistant."},
#                 {"role": "user", "content": f"{prompt}: {target_val}"}
#             ]
#             print("Running LLM enricher with messages: ", messages)
#             #self.synclog(f"Calling LLM: {messages}", callbacks)
#             response = client.chat.completions.create(
#                 model=llm_model,
#                 messages=messages,
#             )
#             if hasattr(response, 'choices') and len(response.choices) > 0:
#                 result = response.choices[0].message.content or ""
#                 print(f"Result: {result}", callbacks)
#             else:
#                 result = "LLM result missing"
#             return result
        
#         con.create_function("llm_enricher", llm_enricher)
        
#         globals()[df_name] = df
#         result = con.execute(f"select *, llm_enricher({source_column}) as {result_column} from {df_name}")
#         df = result.df()

#         return self.get_dataframe_preview(df, name_hint=dataframe_var)
