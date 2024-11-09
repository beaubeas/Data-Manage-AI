import asyncio
import io
from typing import Any, Callable
import re

import pandas as pd
import psycopg2
from psycopg2.extras import DictCursor
import psycopg2.extras

from urllib.parse import urlparse, urlunparse, parse_qs, urlencode
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.engine.triggerable import Triggerable
from supercog.shared.logging import logger


class DatabaseConnectionError(Exception):
    pass

class LocalhostConnectionError(DatabaseConnectionError):
    pass

class DatabaseTool(ToolFactory):
    credentials: dict = {}

    def __init__(self):
        super().__init__(
            id="database",
            system_name="Database",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/8/86/Database-icon.svg",
            category=ToolCategory.CATEGORY_SAAS,
            help="""
General access to most types of databases.
""",
            auth_config = {
                "strategy_token": {
                    "database_type": ["PostgresQL", "Mysql",  "MSSQL"],
                    "database_url": "The Connection URL for the database",
                    "help": " Configure with a connection string, like: postgresql://user:pass@host/database.",
                },
            }
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.run_database_query,
            self.get_database_type,
            self.connect_to_database,
        ])

    def parse_connection_string(self, connection_string: str) -> str:
        """Parse the connection string or CLI command and check for localhost."""
        if '://' in connection_string:  # SQLAlchemy connection string
            parsed = urlparse(connection_string)
            if parsed.hostname in ['localhost', '127.0.0.1']:
                raise LocalhostConnectionError("Connection to localhost is not allowed")

            # Modify the scheme based on the database type
            scheme = parsed.scheme
            if scheme == 'mysql':
                new_scheme = 'mysql+pymysql'
            elif scheme == 'postgresql':
                new_scheme = 'postgresql+psycopg2'
            elif scheme == 'mssql':
                # Convert `mssql+pyodbc` to `mssql+pymssql`
                # Split the netloc part into user credentials and host+port/database
                netloc_parts = parsed.netloc.split('@', 1) if '@' in parsed.netloc else ['', parsed.netloc]
                user_info = netloc_parts[0].split(':', 1) if ':' in netloc_parts[0] else [netloc_parts[0], '']
                user = user_info[0]
                password = user_info[1] if len(user_info) > 1 else ''

                # Split host and port/database
                host_and_port = netloc_parts[1].split('/', 1) if '/' in netloc_parts[1] else [netloc_parts[1], '']
                host = host_and_port[0]
                database = host_and_port[1] if len(host_and_port) > 1 else ''

                # Handle empty values and defaults
                if not user:
                    user = ''
                if not host:
                    raise ValueError("Host is required in the connection string.")
                if not database:
                    database = ''  # Default to empty string if not specified

                # Parse and remove the driver parameter from the query
                query_params = parse_qs(parsed.query)
                query_params.pop('driver', None)
                new_query = urlencode(query_params, doseq=True)

                new_scheme = 'mssql+pymssql'
                # Reconstruct the connection string
                return urlunparse((new_scheme, f"{user}:{password}@{host}", '', '', new_query, ''))
            else:
                new_scheme = scheme  # Keep the original scheme for other databases
            # Reconstruct the connection string with the new scheme
            return urlunparse((new_scheme, parsed.netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
        else:  # CLI command
            # PostgreSQL
            pg_match = re.match(
                r'(?:PGPASSWORD=(\S+)\s+)?psql\s+(?:-h|--host)\s+(\S+)\s+(?:-p|--port)\s+(\d+)?\s+(?:-U|--username)\s+(\S+)(?:\s+(?:-d|--dbname)\s+(\S+))?(?:\s+(\S+))?(?:\s+--set=sslmode=(\S+))?(?:\s+(-W))?', 
                connection_string
            )
            
            if pg_match:
                
                # Unpack matched groups with default values
                password, host, port, user, db_with_d_flag, db_positional, sslmode, prompt_password = pg_match.groups(default='')
                
                # Database can come either from the -d flag or as a positional argument
                database = db_with_d_flag or db_positional
                
                if not database:
                    raise ValueError("Database is required either via -d or as a positional argument.")
                
                # Check for localhost connections (if restriction is needed)
                if host in ['localhost', '127.0.0.1']:
                    raise LocalhostConnectionError("Connection to localhost is not allowed")
                
                # Default port to 5432 if not specified
                port = port or "5432"
                
                # Return formatted connection string for SQLAlchemy
                return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{database}"

            # MySQL
            mysql_match = re.match(
                r'mysql\s+-h\s+(\S+)\s+-P\s+(\d+)\s+-u\s+(\S+)\s+(?:-p\s*(\S*)\s*)?(?:-D\s+(\S+))?', 
                connection_string
            )
            
            if mysql_match:
                
                # Unpack matched groups with default values
                host, port, user, password, database = mysql_match.groups(default='')
                
                # Handle optional password and database
                password = password if password is not None else ''  # No password provided
                database = database if database else ''  # Default to empty string if not specified
                
                # Check for localhost connections (if restriction is needed)
                if host in ['localhost', '127.0.0.1']:
                    raise LocalhostConnectionError("Connection to localhost is not allowed")
                
                # Return the formatted connection string for further use (e.g., SQLAlchemy)
                return f"mysql+pymysql://{user}:{password}@{host}:{port}/{database}"

            # MSSQL
            mssql_match = re.match(
                r'(?:sqlcmd|mssql-cli)\s+-S\s+(\S+)\s+-U\s+(\S+)\s+-P\s+(\S+)(?:\s+-d\s+(\S+))?', 
                connection_string
            )
            
            if mssql_match:
                
                # Unpack matched groups with default values
                tool, host, user, password, database = mssql_match.groups(default='')
                
                # Handle the absence of the -d parameter (optional database)
                if database is None:
                    database = ''  # Default to empty string or set a default value if needed
                
                # Validate for localhost connection restriction
                if host in ['localhost', '127.0.0.1']:
                    raise LocalhostConnectionError("Connection to localhost is not allowed")
                
                # Return the connection string formatted for SQLAlchemy or other usage
                return f"mssql+pymssql://{user}:{password}@{host}/{database}"
            
            # Handle ODBC-style MSSQL connection strings with optional parameters
            odbc_match = re.match(
                r'Server=(\S+)?(?:;Database=(\S+))?(?:;User Id=(\S+))?(?:;Password=(\S+))?;', 
                connection_string
            )
            
            if odbc_match:
                
                # Unpack matched groups with default values
                host, database, user, password = odbc_match.groups(default='')
                
                # Check for localhost connections (if restriction is needed)
                if host in ['localhost', '127.0.0.1']:
                    raise LocalhostConnectionError("Connection to localhost is not allowed")
                
                # Return the connection string formatted for SQLAlchemy or other usage
                return f"mssql+pymssql://{user}:{password}@{host}/{database}"
        raise ValueError("Unable to parse connection string")

    def create_engine(self, connection_string: str):
        """Create a SQLAlchemy engine from the connection string or CLI command."""
        try:
            parsed_connection_string = self.parse_connection_string(connection_string)
            return create_engine(parsed_connection_string)
        except LocalhostConnectionError as e:
            raise e
        except Exception as e:
            raise DatabaseConnectionError(f"Failed to create database engine: {str(e)}")

    def run_database_query(self, sql_query: str) -> dict:
        """ Runs a SQL query against a database."""
        connection_string = self.credentials.get("database_url")
        if not connection_string:
            return {"status": "Connection string is missing"}
        try:
            engine = self.create_engine(connection_string)
            with engine.begin() as connection:
                # Execute the query
                result = connection.execute(text(sql_query))
                
                # Check if the query returns rows
                if result.returns_rows:
                    # Try to read it into a DataFrame
                    try:
                        df = pd.read_sql(sql_query, connection)
                        return self.get_dataframe_preview(df)
                    except:
                        # If it can't be read into a DataFrame, return as list of dicts
                        return {"result": [dict(row) for row in result.mappings()]}
                else:
                    # Query didn't return any rows
                    if result.rowcount is not None and result.rowcount >= 0:
                        return {"status": f"Query executed successfully. Rows affected: {result.rowcount}"}
                    else:
                        return {"status": "Query executed successfully"}
        except LocalhostConnectionError as e:
            return {"status": f"Error: {str(e)}"}
        except DatabaseConnectionError as e:
            return {"status": f"Connection error: {str(e)}"}
        except SQLAlchemyError as e:
            return {"status": f"Database error: {str(e)}"}
        except pd.errors.DatabaseError as e:
            return {"status": f"SQL query error: {str(e)}"}
        except Exception as e:
            return {"status": f"Unexpected error: {str(e)}"}

    def get_database_type(self) -> str:
        """ Returns the type and SQL dialect of the connected database """
        connection_string = self.credentials.get("database_url")
        if not connection_string:
            return "No database URL configured"
        
        try:
            parsed_connection_string = self.parse_connection_string(connection_string)
            dialect = parsed_connection_string.split('://')[0].split('+')[0]
            return dialect.capitalize()
        except LocalhostConnectionError as e:
            return f"Error: {str(e)}"
        except Exception as e:
            return f"Error determining database type: {str(e)}"
        
    @staticmethod
    def get_database_schema(crds_pk: dict) -> str:
        """ Returns the schema for the configured database """
        return ""

    def connect_to_database(self, connection_string: str = None) -> dict:
        """Connects to the database using the provided connection string or the connected database.
        Sample:
        postgresql+psycopg2://username:password@host:port/database
        mysql+pymysql://username:password@host:port/database
        mssql+pymssql://username:password@host:port/database
        """
        if connection_string is None:
            connection_string = self.credentials.get("database_url")

        if not connection_string:
            return {"status": "Connection string is missing"}
        
        try:
            engine = self.create_engine(connection_string)
            with engine.connect() as connection:
                self.credentials = {
                    "database_url": connection_string,
                }
                connection.execute(text("SELECT 1"))
                return {"status": "Connection successful"}
        except LocalhostConnectionError as e:
            return {"status": f"Error: {str(e)}"}
        except DatabaseConnectionError as e:
            return {"status": f"Connection error: {str(e)}"}
        except SQLAlchemyError as e:
            return {"status": f"Database error: {str(e)}"}
        except Exception as e:
            return {"status": f"Unexpected error: {str(e)}"}

    def test_credential(self, cred, secrets: dict) -> str:
        """ Test that the given credential secrets are valid. Return None if OK, otherwise
            return an error message.
        """
        connection_string = secrets.get("database_url")
        if not connection_string:
            return "Connection string is missing"
        
        try:
            engine = self.create_engine(connection_string)
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return None
        except LocalhostConnectionError as e:
            return str(e)
        except DatabaseConnectionError as e:
            return str(e)
        except SQLAlchemyError as e:
            return f"Failed to connect to the database: {str(e)}"
        except Exception as e:
            return f"Unexpected error while testing the connection: {str(e)}"

#         sql = """
# SELECT 
#     table_name, 
#     column_name, 
#     data_type 
# FROM 
#     information_schema.columns
# WHERE 
#     table_schema = 'public' -- Replace 'public' with your schema name if different
#     and table_name not like '\_%'
# ORDER BY 
#     table_name, 
#     ordinal_position;
# """
#         return DatabaseTool.run_database_query(crds_pk, sql)


class DatabaseTriggerable(Triggerable):
    def __init__(self, agent_dict: dict, run_state) -> None:
        super().__init__(agent_dict, run_state)
        self.run_state = run_state
        self.table_name = self.trigger_arg
        m = re.search(r"Database \((.*)\)", self.trigger)
        if m:
            self.cred_name = m.group(1)

    @classmethod
    def handles_trigger(cls, trigger: str) -> bool:
        return trigger.startswith("Database")

    def pick_credential(self, credentials: list) -> bool:
        for cred in credentials:
            if (
                cred.name == self.cred_name and 
                (cred.user_id == self.user_id or (
                    cred.tenant_id == self.tenant_id and
                    cred.scope == "shared"
                ))
            ):
                secrets = cred.retrieve_secrets()
                if 'database_url' not in secrets:
                    logger.error("Db cred {cred.name} has no database_url secret")
                    return False
                self.db_url = secrets['database_url']
                return True
        return False

    async def run(self):
        try: 
            await self.__run()
        except Exception as e:
            logger.error("Error running database poller: ", e)

    async def __run(self):
        # Polls for the new records in the indicated table. The table should have some sorting
        # key that allows us to detect "new" records. For now we use the implicit 'ctid'
        # column as a hack (since those values can change if the table is modified).
        print("running database trigger on ", self.db_url)
        #conn = psycopg2.connect(self.db_url)
        conn = psycopg2.extras.DictConnection(self.db_url)
        curs = conn.cursor(cursor_factory=DictCursor)

        def get_last_xmin():
            curs.execute(f"SELECT max(xmin::text::bigint) FROM {self.table_name}")
            row = curs.fetchone()
            if row:
                if isinstance(row[0], dict):
                    return row.values()[0]
                else:
                    return row[0]
            return '(0,0)' # assuming this will work for an empty table - we should test it

        last_xmin = get_last_xmin()
        print("last xmin is: ", last_xmin)
        while await self.run_state.is_running():
            query = f""" 
    SELECT *, xmin::text::bigint as xmin FROM {self.table_name} WHERE xmin::text::bigint > %s ORDER BY ctid
            """
            #print(query, (last_xmin,))
            curs.execute(query, (last_xmin,))
            rows = curs.fetchall()
            for row in rows:
                print("New record: ", row)
                last_xmin = int(row['xmin'])
                try:
                    run = self.create_run(dict(row))
                    print("Ran agent: ", run)
                except Exception as e:
                    logger.error("Error running agent: ", e)
            await asyncio.sleep(3) # poll db every 3 seconds. This should be configurable
        logger.info("Quitting db poller thread by flag")            

