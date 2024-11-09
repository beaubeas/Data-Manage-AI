# Files and data

The LLMs are not naturally great at manipulating data. That said, GPT4 is 
pretty compentent and reading and writing CSV data, for example.

But for larger data sets we will mostly need to process data outside of
the LLM.

To do this, we can adopt `DataFrames` as a common representation of tabluar
data, and have the Engine service keep track of DataFrames being used by
agents.

To return tabluar data from a function, we can return just a 
handle name, like:

    dataframe_a123

And then pass that value to subsequent functions that need to reference the data.

Potentially, to allow some richer handling in the LLM, we could
return a JSON "preview" of the datafame:

    {
        "type":"dataframe",
        "name": "dataframe_a123",
        "columns": ["name","email","created_at","amount"],
        "row_count": 2000,
        "preview": [
            [
                "scott","scott@google.com","2024-12-12","100",
                "scott","scott@google.com","2024-12-12","100"
            ]
        ]
    }

And our functions which take tabular data should support taking
either version as inputs.

## Dataframe storage

Agents should assume they can always retrieve the contents of any dataframe.
In practice we may store dataframes in memory, or in Redis, or even save
them to files.

## How to handle files and databases

If your tool needs to work with tabular data you should prefer to use
DataFrames. 

Separately we can create reader/writer tools that allow us to read and write
DataFrames into different formats (spreadsheets, CSV, database). One nice
thing about dataframes is that they can interoperate between files and databases.

The UX for dealing with files and dataframes should be natural and implicit,
mostly referring back to the source file. So you should be able to do like:

    please read the file contacts.csv
    what are the last 5 rows?
    please write the contacts out in parquet format

and have the agent "do the right thing" even though the CSV data is never
all inserted into the context.

So this conversation should translate into these function calls:

    read_file_into_dataframe("contacts.csv") <- returns df preview
    get_dataframe_as_text("contacts_df133", start_row=95, max_rows=5)
    write_dataframe_to_file("contacts.parquest", "contacts_df133")

Although I guess it's ambiguous whether the write call should write ALL
the contacts or just the last five rows.

It's possible that if you have attached the Pandas tool, then it should
inject instructions telling the LLM how dataframe variables work. We can
test that but hopefully careful naming will take care of it.


## Chat-uploaded files

The Dashboard supports uploading a file as part of the chat interaction. In
this case the file is uploaded first to the dashboard server, then transparently
posted to the Engine when the user submits the accompanying text prompt. We
also inject a quick note about the file into the prompt so that the LLM knows
that it is there, AND we silently attach a tool that allows the LLM to read
the contents of the file. Ideally we can auto-detect the type of the file
and attached _just_ the right function for reading that type of file.

To avoid filename conflicts, we should put the file inside a folder using
the RunID so that files in that chat are separate from any other files. The
Chat interface should offer a feature for the user to "store" the file long
term by moving it into the long-term storage folder where any Agent can
see it.


