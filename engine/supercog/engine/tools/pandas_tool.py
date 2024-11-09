from supercog.engine.tool_factory import ToolFactory, ToolCategory
import pandas as pd
import numpy as np

from typing   import Any, Callable

class PandasTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "pandas_tools",
            system_name = "Pandas",
            logo_url="https://icon.icepanel.io/Technology/svg/Pandas.svg",
            auth_config = {},
            category=ToolCategory.CATEGORY_FILES,
            help="""
Manipulate dataframes, and convert file formats into dataframes.
"""
        )
    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.read_file_as_dataframe,
            self.read_file_as_text,
            self.add_column_to_dataframe,
            self.get_dataframe_as_text,
            self.write_dataframe_to_file,
        ])

    def _infer_format_from_name(self, file_name: str) -> str:
        if file_name.endswith(".csv"):
            return "csv"
        elif file_name.endswith(".parquet"):
            return "parquet"
        elif file_name.endswith(".xlsx"):
            return "excel"
        else:
            raise RuntimeError(f"Can't infer format from file name '{file_name}'")
            
    def read_file_as_dataframe(
        self,
        file_name,
        file_format:str="infer"
    ) -> dict:
        """ Reads the indicated file and returns the contents as a DataFrame preview.
            File format should be "infer", "csv", "parquet", or "excel".
        """
        if file_format == "infer":
            file_format = self._infer_format_from_name(file_name)

        if file_format == "csv":
            df = pd.read_csv(file_name)
        elif file_format == "parquet":
            df = pd.read_parquet(file_name)
        elif file_format == "excel":
            df = pd.read_excel(file_name, engine='openpyxl')
        else:
            return {"status": "error", "message": "File format not recognized"}    
        
        return self.get_dataframe_preview(df, name_hint=file_name)

    def read_file_as_text(
        self,
        file_name,
    ) -> str:
        """ Reads the indicated file and returns the contents as text. Only
            use this function if the file doesn't seem to be in a format that
            can be read as a DataFrame.
        """
        return open(file_name).read()

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
    
    def get_dataframe_as_text(
        self,
        dataframe_var: str,
        start_row: int = 0,
        total_rows: int|None=None,
    ) -> str:
        """ Returns the contents of the indicated DataFrame as a string. You can limit
            the rows returned using start_row and total_rows parameters. """
        df, _ = self.get_dataframe_from_handle(dataframe_var)
        if total_rows is not None:
            df = df.iloc[start_row:start_row+total_rows]
        elif start_row > 0:
            df = df.iloc[start_row:]
        return df.to_string(index=False)
    
    def write_dataframe_to_file(
        self,
        dataframe_var: str,
        file_name,
        file_format="infer",
    ) -> dict:
        """ Writes the indicated DataFrame to the indicated file. File_format
            can be one of: "infer", "csv", "parquet", or "excel".
        """
        df, df_name = self.get_dataframe_from_handle(dataframe_var)

        if file_format == "infer":
            file_format = self._infer_format_from_name(file_name)

        if file_format == "csv":
            df.to_csv(file_name, index=False)
        elif file_format == "parquet":
            df.to_parquet(file_name)
        elif file_format == "excel":
            df.to_excel(file_name, index=False)
        else:
            return {"status": "error", "message": f"File format '{file_format}' not recognized"}

        return {"status":"success"}

