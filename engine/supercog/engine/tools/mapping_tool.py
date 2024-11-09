import os
import json
import requests
import datetime
from typing import Any, Callable, Optional
import pandas as pd
from supercog.engine.tool_factory import ToolFactory, ToolCategory

class MappingTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "mapping_connector",
            system_name = "Mapping",
            logo_url="/mapping-icon.png",
            auth_config = { },
            help="""
Move data between multiple systems
""",
            category=ToolCategory.CATEGORY_BUILTINS
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.integrate,
        ])
       
    @staticmethod
    def rename_field( row, name_mapping) -> dict:
        """ Rename the field for mapping """
        source_name = row["Original_Name"]
        # Use name_mapping dictionary to get new name and target object
        new_name = name_mapping.get(source_name)  # Handle potential missing keys
        # in the future we might have an object name in the third column
        #if new_name:
        #    target_object = new_name[2]  # Assuming target object is at index 2 in the mapping value
        #else:
        #    Handle cases where the source name is not found in the mapping (optional)
        #    target_object = None
        return {source_name: new_name} if new_name else {}
    
    #def transform_column():
        # For the future we may implement transforms here if they are not handled earlier by the LLM.
        # Convert data formats if needed (e.g., dates). These transformations should be specified
        # in the mapping  as a third column. We would like to use english language to descibe
        # the mappings and have a pass over the mappings  to convert the english language to
        # pandas formatting functions before we get into this mapping_tool.
        # i.e.:
        # df['Renewal_Date__c'] = pd.to_datetime(df['Renewal_Date__c']).dt.strftime('%Y-%m-%d')
    
    def integrate(
        self,
        source_csv,
        target_csv,
        mappings: dict,
        ) -> str:
        """ Move data between systems using source csv and target csv and mapping files 
        Keyword arguments:
        source_csv  -- the file name of the source file with the column names and data to be mapped
        target_csv: -- the file name of the tyarget file
        mappings:   -- A dictionary with the mapping definitions in two or three columns
        """            
        if not os.path.exists(source_csv):
            return f"Error: cannot find input file {source_csv}"
        
        source_df = pd.read_csv(source_csv)
        # Map the columns in to the columns out
        target_df = source_df.rename(columns=mappings)
        
        #target_df = source_df.apply(MappingTool.rename_field, axis=1, args=(mappings,))
        
        # Save the target dataframe
        target_df.to_csv(target_csv, index=False)

        return "Mapping complete"
        # Note: The script assumes that the input CSV file has the same column names as the
        # "Excel Column Name" from the mappings.
        # If the input CSV has different column names, you will need to adjust the 'mappings'
        # dictionary accordingly.

        
