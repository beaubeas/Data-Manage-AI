import re
from typing import Literal

def inline_markdown_to_rich_text(line: str, is_list_or_quote: bool = False):
    # Define inline formatting patterns with capturing groups
    patterns = [
        (r'\*\*\*(.+?)\*\*\*', {"bold": True, "italic": True}), # Bold & Italic
        (r'\_\_\_(.+?)\_\_\_', {"bold": True, "italic": True}), # Bold & Italic
        (r'\_\_\*(.+?)\*\_\_', {"bold": True, "italic": True}), # Bold & Italic
        (r'\*\*\_(.+?)\_\*\*', {"bold": True, "italic": True}), # Bold & Italic
        (r'\*\*(.+?)\*\*', {"bold": True}),                     # Bold
        (r'\_\_(.+?)\_\_', {"bold": True}),                     # Bold
        (r'\*(.+?)\*', {"italic": True}),                       # Italic
        (r'\_(.+?)\_', {"italic": True}),                       # Italic
        (r'\`(.+?)\`', {"code": True}),                         # Inline code
        (r'\~(.+?)\~', {"strike": True}),                       # Strikethrough
        (r'\!?\[(.+?)\]\((.+?)\)', {"link": True})                 # Links
    ]
    
    # Combine all patterns into one unified regex to capture all inline formats
    combined_pattern = '|'.join([f"(?:{pattern})" for pattern, _ in patterns])

    # This pattern will also capture the non-formatted text
    token_pattern = re.compile(rf"({combined_pattern}|[^\*\_\`~\[\]]+)")

    # Match all tokens (either formatted text or plain text)
    tokens = token_pattern.findall(line)
    
    elements = []
    for token in tokens:
        matched = False
        # Check each token for a match with the inline formatting patterns
        for idx, (pattern, style) in enumerate(patterns):
            matched_text = token[idx + 1]  # Capture group for the matched text
            if matched_text:
                matched = True
                if style == {"link": True}:  # Handle links specially
                    link_text = token[idx + 1]
                    link_url = token[idx + 2]
                    elements.append({
                        "type": "link",
                        "text": link_text,
                        "url": link_url
                    })
                else:
                    # For other inline formats (bold, italic, etc.)
                    elements.append({
                        "type": "text",
                        "text": matched_text,
                        "style": style
                    })
                break
        
        if not matched:
            # If it's not a match (plain text), add it as normal text
            elements.append({
                "type": "text",
                "text": token[0]  # Token is plain text (no format)
            })
        
    if len(elements) == 0:
        elements.append({
            "type": "text",
            "text": ""
        })
        
    # Add \n\n to the last element of the line
    if not is_list_or_quote:
        elements[-1]["text"] += "\n\n"
    
    return elements

def list_markdown_to_rich_text(slack_blocks: list, line: str, list_type: Literal["bullet", "ordered"]):
    # If the top level list is ordered use indent of 3, otherwise 2
    indent_break = 2
    if (len(slack_blocks) > 0 and
        slack_blocks[-1].get("type") == "rich_text" and
        len(slack_blocks[-1]["elements"]) > 0 and
        slack_blocks[-1]["elements"][-1].get("style", "") == "ordered"):
        indent_break = 3

    indent_level = int((len(line) - len(line.lstrip())) / indent_break)

    list_item = line.lstrip().split(' ', 1)[1].strip()  # Remove leading `-`, `*`, or number
    elements = inline_markdown_to_rich_text(list_item, True)
    rich_text_list_element = {
        "type": "rich_text_section",
        "elements": elements
    }
    rich_text_element = {
        "type": "rich_text_list",
        "style": list_type,
        "indent": indent_level,
        "elements": [rich_text_list_element],
    }
    
    # If there is no rich_text block create one
    if len(slack_blocks) == 0 or slack_blocks[-1].get("type") != "rich_text":
        slack_blocks.append({
            "type": "rich_text",
            "elements": [rich_text_element],
        })
    # If there are no rich_text elements
    elif len(slack_blocks[-1]["elements"]) == 0:
        slack_blocks[-1]["elements"] = [rich_text_element]
    # If there is no rich_text_list as the most recent element
    elif slack_blocks[-1]["elements"][-1].get("type") != "rich_text_list":
        slack_blocks[-1]["elements"].append(rich_text_element)
    # If the most recent rich_text_list indentation does not match
    elif slack_blocks[-1]["elements"][-1].get("indent", 0) != indent_level:
        slack_blocks[-1]["elements"].append(rich_text_element)
    # If the most recent rich_text_list style does not match
    elif slack_blocks[-1]["elements"][-1].get("style") != list_type:
        # Need an extra block between them
        slack_blocks[-1]["elements"].append({
            "type": "rich_text_section",
            "elements": [{
                "type": "text",
                "text": "\n"
            }],
        })
        slack_blocks[-1]["elements"].append(rich_text_element)
    # If the most recent rich_text_list has no elements
    elif len(slack_blocks[-1]["elements"][-1]["elements"]) == 0:
        slack_blocks[-1]["elements"][-1]["elements"] = [rich_text_list_element]
    else:
        slack_blocks[-1]["elements"][-1]["elements"].append(rich_text_list_element)

def blockquote_markdown_to_rich_text(slack_blocks: list, line: str):
    matches_length = len(re.match(r'^(> )+', line.lstrip()).group())
    border = 1 if matches_length > 2 else 0

    quote_text = re.sub(r'^(> )+', "", line.lstrip(), 1).strip()
    elements = inline_markdown_to_rich_text(quote_text, True)

    # Add a \n to the last element's text
    if len(elements) > 0:
        elements[-1]["text"] += "\n"

    rich_text_element = {
        "type": "rich_text_quote",
        "border": border,
        "elements": elements
    }

    # If there is no rich_text block create one
    if len(slack_blocks) == 0 or slack_blocks[-1].get("type") != "rich_text":
        slack_blocks.append({
            "type": "rich_text",
            "elements": [rich_text_element]
        })
    # If there are no rich_text elements
    elif len(slack_blocks[-1]["elements"]) == 0:
        slack_blocks[-1]["elements"] = [rich_text_element]
    # If there is no rich_text_quote as the most recent element
    elif slack_blocks[-1]["elements"][-1].get("type") != "rich_text_quote":
        slack_blocks[-1]["elements"].append(rich_text_element)
    # If the most recent rich_text_quote indentation does not match
    elif slack_blocks[-1]["elements"][-1].get("border", 0) != border:
        slack_blocks[-1]["elements"].append(rich_text_element)
    # If the most recent rich_text_quote has no elements
    elif len(slack_blocks[-1]["elements"][-1]["elements"]) == 0:
        slack_blocks[-1]["elements"][-1]["elements"] = elements
    else:
        slack_blocks[-1]["elements"][-1]["elements"].extend(elements)
        
def markdown_to_slack_rich_text(markdown_text: str):
    """
    Convert Markdown text to Slack rich text format.
    
    Parameters:
    markdown_text (str): The Markdown text to be converted.
    
    Returns:
    list: A list of Slack rich text block objects.
    """
    slack_blocks = []
    
    # Split the Markdown text into lines
    lines = markdown_text.split('\n')
    
    # Keep track of code block state
    in_code_block = False
    
    # Iterate through the lines and convert to Slack blocks
    for line in lines:
        # Check for code blocks
        if line.startswith('```'):
            if not in_code_block:
                # Start of a code block
                in_code_block = True
                slack_blocks.append({
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_preformatted",
                            "elements": []
                        }
                    ]
                })
            else:
                # End of a code block
                in_code_block = False
        # If in a code block, add the line as-is
        elif in_code_block:
            slack_blocks[-1]["elements"][0]["elements"].append({
                "type": "text",
                "text": f"{line}\n",
            })
        # Check for headers
        elif line.startswith('#'):
            level = line.count('#')
            text = line[level:].strip()
            if text:
                slack_blocks.append({
                    "type": "header",
                    "text": {
                        "type": "plain_text",
                        "text": text,
                        "emoji": True
                    }
                })
        # Check for dividers
        elif line.strip() == '---':
            slack_blocks.append({
                "type": "divider"
            })
        # Check for unordered lists (start with `-` or `*`)
        elif line.lstrip().startswith(('- ', '* ')):
            list_markdown_to_rich_text(slack_blocks=slack_blocks, line=line, list_type="bullet")
        # Check for ordered lists (lines starting with a number followed by a dot)
        elif re.match(r'^\d+\. ', line.lstrip()):
            list_markdown_to_rich_text(slack_blocks=slack_blocks, line=line, list_type="ordered")
        # Check for blockquotes (lines starting with `> `)
        elif re.match(r'^(> )+', line.lstrip()) is not None:
            blockquote_markdown_to_rich_text(slack_blocks=slack_blocks, line=line)
        # All other lines are treated as rich text
        else:
            # Check if the last block is rich text, if not create a new one
            previous_block_is_rich_text = len(slack_blocks) > 0 and slack_blocks[-1].get("type") == "rich_text"

            if not previous_block_is_rich_text:
                slack_blocks.append({
                    "type": "rich_text",
                    "elements": []
                })

            elements = inline_markdown_to_rich_text(line)

            # Add the constructed elements to the Slack block
            if elements:
                slack_blocks[-1]["elements"].append({
                    "type": "rich_text_section",
                    "elements": elements,
                })
    
    return slack_blocks
