from typing import List, Callable
import pandas as pd
import duckdb

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LLMFullResult, LangChainCallback


class BasicDataTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="basic_data_functions",
            system_name="Basic Data",
            logo_url="",
            auth_config={},
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.load_full_preview_content,
# FIXME: Only attach the query_dataframe function after a tool returns a dataframe result
#            self.query_dataframe,
        ])

    def load_full_preview_content(self, var_name: str) -> str:
        """ If a tool function returns a preview, call this function to retrieve the entire result. """
        try:
            data = self.get_data_from_handle(var_name)
        except:
            return f"No data found with name {var_name}."

        if isinstance(data, pd.DataFrame):
            return LLMFullResult(str(data[0:1000].to_csv(index=False)))
        elif data is not None:
            if isinstance(data, str):
                return LLMFullResult(data)
            else:
                return LLMFullResult(str(data))
        else:
            return f"Error: no dataframe found  name {var_name}."

    async def query_dataframe(
            self,
            dataframe_var: str,
            sql_query: str,
            result_name: str|None=None,
    ):
        """ Uses DuckDB to query from a dataframe using SQL. Returns a new dataframe
            from the query result. Use this function to rename columns, or add or
            drop columns from a dataframe.
        """
        df, df_name = self.get_dataframe_from_handle(dataframe_var)
        globals()[df_name] = df
        await self.log(f"Querying DataFrame {df_name} with query: '{sql_query}'")
        result = duckdb.sql(sql_query)
        df = result.df()
        return self.get_dataframe_preview(df, name_hint=result_name or df_name, sanitize_column_names=False)
    
