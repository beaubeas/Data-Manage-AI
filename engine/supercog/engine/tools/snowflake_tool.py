import csv
from contextlib import contextmanager
import pandas as pd
from typing import Callable, Any, Optional
from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback
import snowflake.connector

from langchain.callbacks.manager import (
    AsyncCallbackManager
)

#"protocol": "https",
#"host": "<host>",
#"port": "443",



class SnowflakeTool(ToolFactory):
    class Config:
        arbitrary_types_allowed=True

    connection: snowflake.connector.connection.SnowflakeConnection = None
    callbacks: LangChainCallback = None

    def __init__(self):
        super().__init__(
            id = "snowflake_connector",
            system_name = "Snowflake",
            logo_url=super().logo_from_domain("snowflake.com"),
            auth_config = {
                "stategy_token": {
                    "Account name": "Your snowflake account",
                    "User Name":    "Your snowflake username",
                    "Password":     "The password for your snowflake account",
                    "Warehouse":    "Your warehouse for execution",
                    "help": """
Enter your Snowflake account, user name and password
"""
                }
            },
            help="""
Access Snowflake data
""",
            category=ToolCategory.CATEGORY_SAAS
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.run_snowflake_sql,
            self.list_databases,
            self.upload_dataframe_to_snowflake,
        ])

    @contextmanager
    def cursor(self, callbacks: LangChainCallback):
        self.callbacks = callbacks
        if self.connection is None:
            self.connection = snowflake.connector.connect(
                user=      self.credentials.get("User Name"),
                password=  self.credentials.get("Password"),
                account=   self.credentials.get("Account name"),
                warehouse= self.credentials.get("Warehouse"),
            )
        yield self.connection.cursor()

    async def runsql(self, cursor, sqlstring: str):
        await self.log(f"Executing SQL '{sqlstring}'\n", self.callbacks)
        return cursor.execute(sqlstring)

    async def list_databases(self, callbacks: LangChainCallback):
        """ List all the databases in the Snowflake warehouse. """
        with self.cursor(callbacks) as cursor:
            res = await self.runsql(cursor, "SHOW DATABASES")
            return res.fetchall()

    async def run_snowflake_sql(
        self,
        database:  str,
        snowflake_schema:    str,
        sqlstring: str,
        callbacks: LangChainCallback,
        ) -> dict:
        """ execute SQL commands on snowflake """

        with self.cursor(callbacks) as cursor:
            await self.runsql(cursor, f"USE DATABASE {database};")
            await self.runsql(cursor, f"USE SCHEMA {snowflake_schema};")

            return await self.result_as_dataframe(await self.runsql(cursor, sqlstring), cursor)                     

    async def result_as_dataframe(self, result, cursor):
        try:
            return self.get_dataframe_preview(result.fetch_pandas_all())
        except Exception as e:
            print("Conver to pandas failed first: ", e)
            df = pd.DataFrame.from_records(iter(cursor), columns=[x[0] for x in cursor.description])
            return self.get_dataframe_preview(df)

    def test_credential(self, cred, secrets: dict) -> Optional[str]:
            """ Test that the given credential secrets are valid. Return None if OK, otherwise
                return an error message.
            """

            try:
                conn = snowflake.connector.connect(
                    user=secrets.get("User Name"),
                    password=secrets.get("Password"),
                    account=secrets.get("Account name"),
                    warehouse=secrets.get("Warehouse"),
                )
                print("Connection tested OK!")
                conn.close()
                return None
            except Exception as e:
                return str(e)

    async def upload_dataframe_to_snowflake(
        self,
        dataframe_var: str,
        database: str,
        snowflake_schema: str,
        create_table: bool = False,
        table_name: str = "",
        table_create_statement: str = "",
        callbacks: LangChainCallback=None,
        ):
        """ Upload data into a Snowflake table. Pass 'create_table=True' if you want to create or
            drop/create the table, otherwise the table must already exist. 

            The 'table_create_statement' is only required if 'create_table=True' and is the SQL
            statement to create the table. If 'create_table=False', this parameter is ignored.

            Pass the input data as the variable name of a dataframe.
            """

        with self.cursor(callbacks) as cursor:
            await self.runsql(cursor, f"USE DATABASE {database};")
            await self.runsql(cursor, f"USE SCHEMA {snowflake_schema};")
            if create_table:
                await self.log(f"Creating table {table_name}\n", callbacks)
                await self.runsql(cursor, f"DROP TABLE IF EXISTS {database}.{snowflake_schema}.{table_name}")

            if create_table and table_create_statement:
                if not table_create_statement.lower().startswith("create table"):
                    table_create_statement = f"CREATE TABLE {database}.{snowflake_schema}.{table_name} " + table_create_statement
                await self.runsql(cursor, table_create_statement)

            df, df_name = self.get_dataframe_from_handle(dataframe_var)
            filename = "upload1.parquet"
            df.to_parquet(filename, index=False)

            await self.runsql(cursor, "CREATE FILE FORMAT IF NOT EXISTS sc_parquet_format;");
            await self.runsql(cursor, "CREATE OR REPLACE STAGE supercog FILE_FORMAT = sc_parquet_format;")
            await self.runsql(cursor, f"PUT file://{filename} @supercog")
            cmd = f"""
            COPY INTO {database}.{snowflake_schema}.{table_name} 
                 FROM @supercog
              PATTERN = '{filename}'
              FILE_FORMAT = (TYPE = PARQUET)
              MATCH_BY_COLUMN_NAME=CASE_INSENSITIVE ON_ERROR=CONTINUE FORCE=TRUE;
            """
            #field_optionally_enclosed_by='""' 
            res = await self.runsql(cursor, cmd)
            return await self.result_as_dataframe(res, cursor)
    
