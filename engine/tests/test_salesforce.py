import asyncio
import json
from supercog.engine.tools.salesforce import SalesforceTool  # Assuming this is how you import your SalesforceTool

async def test_call_metadata_api():
    # Initialize the SalesforceTool
    sf_tool = SalesforceTool()
    
    # Prepare the credentials (you'll need to implement this part based on your authentication setup)
    await sf_tool.prepare_creds(your_credential_object, your_secrets_dict)

    # Call the Metadata API to list custom objects
    result = await sf_tool.call_metadata_api("list_metadata", {"type": "CustomObject"})
    
    # Parse the JSON result
    metadata_list = json.loads(result)
    
    # Check if we got a list of metadata items
    if isinstance(metadata_list, list):
        print("Successfully retrieved custom objects:")
        for item in metadata_list:
            print(f"- {item['fullName']}")
    else:
        print("Error or unexpected response:")
        print(result)

# Run the test
if __name__ == "__main__":
    asyncio.run(test_call_metadata_api())