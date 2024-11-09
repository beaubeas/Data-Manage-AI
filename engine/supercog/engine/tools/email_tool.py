from typing import Callable

import markdown2
from premailer import transform
import css_inline

from supercog.shared.utils import send_mail_ses
from supercog.shared.services import config
from supercog.shared.apubsub import RequestVarsEvent
from .utils import markdown_to_html

from supercog.engine.tool_factory import ToolFactory, ToolCategory, LangChainCallback

class BasicEmailerTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id = "basic_emailer",
            system_name = "Send Email (built-in)",
            logo_url="https://banner2.cleanpng.com/20180605/qke/kisspng-computer-icons-email-clip-art-5b1643c0644c28.2686936815281857924108.jpg",
            auth_config = {},
            category=ToolCategory.CATEGORY_EMAIL,
            tool_uses_env_vars=True,
            help="""
Send email via the built-in email system.
"""
        )
    def get_tools(self) -> list[Callable]:
        return self.wrap_tool_functions([
            self.send_email,
            self.send_mail_to_current_user,
        ])


    async def send_mail_to_current_user(
        self,
        subject: str,
        body: str,
        source_format: str = "markdown",
    ) -> str:
        """ Send an email message to the indicated address. The 'to' address can be 'current_user'
            or a natural address. Give the message text format as either 'text' or 'markdown'. """

        return await self.send_email("current_user", subject, body, source_format)

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        source_format: str = "markdown",
    ) -> str:
        """ Send an email message to the indicated address. 
            Give the message text format as either 'text' or 'markdown'. 
        """
        from_addr = config.get_email_sender()
        if to == "current_user":
            to = self.run_context.get_current_user_email()
        else:
            to = self.run_context.resolve_secrets(to)
            whitelist = self.run_context.get_env_var("EMAIL_WHITELIST")
            if whitelist is None:
                return "You must set the EMAIL_WHITELIST env var to a comma separated list of recipients."
            
            if to not in whitelist:
                return str({"error": f"Recipient '{to}' does not appear on EMAIL_WHITELIST"})
            
        await self.log("Sending email to: ", to)

        body_plain_text = body

        if source_format == 'markdown':
            body_html = self.markdown_to_email_html(body)
        else:
            body_html = body_plain_text

        res = send_mail_ses(from_addr, to, subject, text_body=body_plain_text, html_body=body_html)
        return str(f"Sent message {res} to: {to}")


    def markdown_to_email_html(self, markdown_text, css=None) -> str:
        # Convert Markdown to HTML using markdown2
        extras = ["fenced-code-blocks", "tables", "break-on-newline"]
        html = markdown2.markdown(markdown_text, extras=extras)
        
        # Basic email-friendly CSS
        default_css = """
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        h1, h2, h3 { color: #2c3e50; }
        a { color: #3498db; }
        pre { background-color: #f8f8f8; border: 1px solid #ddd; padding: 10px; }
        blockquote { border-left: 3px solid #ccc; margin: 0; padding-left: 10px; color: #555; }
        """
        
        # Combine default CSS with any custom CSS
        full_css = default_css + (css or "")
        
        # Wrap the HTML content
        wrapped_html = f"""
        <html>
        <head>
            <style>{full_css}</style>
        </head>
        <body>{html}</body>
        </html>
        """
        
        # Inline the CSS
        inlined_html = transform(wrapped_html)
        
        # Additional inlining for better compatibility
        inliner = css_inline.CSSInliner()
        final_html = inliner.inline(inlined_html)

        return final_html

