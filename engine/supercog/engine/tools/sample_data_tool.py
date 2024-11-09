import json
import csv
import os
from typing import List, Any, Callable
from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config
from openai import OpenAI

class SampleDataTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="sample_data",
            system_name="Sample Data",
            logo_url="https://upload.wikimedia.org/wikipedia/commons/5/5c/Crystal_spreadsheet.png",
            category=ToolCategory.CATEGORY_FILES,
            auth_config={},
            help="""
Use this tool when you need to generate some sample data for testing an agent.
The tool creates intelligent, realistic sample data.
"""
        )

    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.create_sample_csv,
            self.generate_sample_csv,
        ])

    def create_sample_csv(self, column_names: List[str], filename: str, rows: List[List[str]]):
        """
        Creates a CSV file with the specified column names and rows.

        :param column_names: A list of column names for the CSV.
        :param filename: The name of the file to write to S3.
        :param rows: A list of lists, where each inner list represents a row of data.
        """
        try:
            # Define the path for the temporary file
            temp_path = f"{filename}"

            # Create and write the CSV file locally
            with open(temp_path, 'w', newline='') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(column_names)
                writer.writerows(rows)

            # Save the CSV using the superclass method
            #result = self.put_file(filename, temp_path)
            #os.remove(temp_path)

            return {"status": "success", "message": f"CSV file '{filename}' created and uploaded successfully"}
        except Exception as e:
            print(f"Error in create_sample_csv: {str(e)}")
            return {"status": "error", "message": f"Failed to create or upload CSV file: {str(e)}"}

    def generate_sample_csv(self, data_type: str, filename: str):
        """
        Generates a CSV file with random contents based on the specified data type.

        :param data_type: A string specifying the type of data to generate.
        :param filename: The name of the CSV file to be created and stored.
        """
        try:
            print(f"Generating sample CSV for data type: {data_type}")
            
            # Call the OpenAI API to interpret the data type and generate sample data
            sample_data = self.get_sample_data_from_openai(data_type)
            
            print(f"Received sample data: {sample_data}")
            
            # Validate the returned data
            if not isinstance(sample_data, dict):
                raise ValueError(f"Expected dict, got {type(sample_data)}")
            
            if 'column_names' not in sample_data:
                raise ValueError("'column_names' not found in sample data")
            
            if 'rows' not in sample_data:
                raise ValueError("'rows' not found in sample data")
            
            # Additional type checking
            if not isinstance(sample_data['column_names'], list):
                raise ValueError(f"Expected list for 'column_names', got {type(sample_data['column_names'])}")
            
            if not isinstance(sample_data['rows'], list):
                raise ValueError(f"Expected list for 'rows', got {type(sample_data['rows'])}")

            # Write the generated data to a CSV file
            result = self.create_sample_csv(sample_data['column_names'], filename, sample_data['rows'])
            print(f"Sample CSV generation result: {result}")
            return result
        except Exception as e:
            print(f"Error generating sample CSV: {str(e)}")
            return {"status": "error", "message": str(e)}

    def get_sample_data_from_openai(self, description: str) -> dict:
        """
        Calls the OpenAI API to generate sample data based on the description.

        :param description: A string describing the type of data to generate.
        :return: A dictionary with 'column_names' and 'rows' keys containing the generated data.
        """
        messages = [
            {"role": "system", "content": "You are a helpful assistant that generates sample data in JSON format."},
            {"role": "user", "content": f"Generate a sample CSV with the following type of data: '{description}'. Respond with a JSON object containing 'column_names' (a list of column names) and 'rows' (a list of lists, where each inner list represents a row of data). Generate at least 5 rows of data. Ensure all data is in string format."}
        ]
        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            print(f"OpenAI API response: {content}")
            
            # Parse and validate the JSON response
            data = json.loads(content)
            if not isinstance(data, dict) or 'column_names' not in data or 'rows' not in data:
                raise ValueError("Invalid data structure in OpenAI API response")
            
            return data
        except Exception as e:
            print(f"Error in OpenAI API call: {str(e)}")
            raise
