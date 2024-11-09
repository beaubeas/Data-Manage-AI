import os
from supercog.engine.tool_factory import ToolFactory, TOOL_REGISTRY

from supercog.engine.tools.admin_tool               import AdminTool
from supercog.engine.tools.auth_rest_api_tool       import AuthorizedRESTAPITool
from supercog.engine.tools.caldav_tool              import CalDAVTool
from supercog.engine.tools.auto_dynamic_tools       import AutoDynamicTools
from supercog.engine.tools.csv_tool                 import CSVTool
from supercog.engine.tools.code_interpreter_tool    import CodeInterpreterTool
from supercog.engine.tools.database_tool            import DatabaseTool
from supercog.engine.tools.discord_tool             import DiscordTool
from supercog.engine.tools.dynamic_agent_tool       import DynamicAgentTool
from supercog.engine.tools.duckdb                   import DuckdbTool
from supercog.engine.tools.email_tool               import BasicEmailerTool
from supercog.engine.tools.emotion_logic            import EmotionLogicTool
from supercog.engine.tools.excel_tool               import ExcelTool
from supercog.engine.tools.file_download_tool       import FileDownloadTool
from supercog.engine.tools.ftp_tool                 import FTPTool
from supercog.engine.tools.gdocs_tool               import GoogleDocsTool
from supercog.engine.tools.generate_image           import ImageGeneratorTool
from supercog.engine.tools.gmail_tool               import GmailAPITool
from supercog.engine.tools.git_tool                 import GitTool
from supercog.engine.tools.google_calendar_tool     import GoogleCalendarTool
from supercog.engine.tools.google_news_tool         import GoogleNewsTool
from supercog.engine.tools.HubspotCRMTool           import HubspotCRMTool
from supercog.engine.tools.imap_tool                import IMAPTool
from supercog.engine.tools.image_analysis           import ImageAnalysisTool
from supercog.engine.tools.jira_tool                import JIRATool
from supercog.engine.tools.linkedin_data_tool       import LinkedinDataTool
from supercog.engine.tools.local_folder_doc_source  import LocalFolderDocSource
from supercog.engine.tools.mapping_tool             import MappingTool
from supercog.engine.tools.MatplotlibChartTool      import MatplotlibChartTool
from supercog.engine.tools.memory_compression_tool  import MemoryCompressionTool
from supercog.engine.tools.notion                   import NotionDocSource
from supercog.engine.tools.nmap_tool                import NmapTool
from supercog.engine.tools.pandas_tool              import PandasTool
from supercog.engine.tools.playwright_tool          import PlaywrightTool
from supercog.engine.tools.rag_tool                 import RAGTool
from supercog.engine.tools.read_file                import ReadFileTool
from supercog.engine.tools.reflection_tool          import ReflectionTool
from supercog.engine.tools.rest_api_tool            import RESTAPITool
from supercog.engine.tools.rest_tool_v2             import RESTAPIToolV2
from supercog.engine.tools.s3_tool                  import S3Tool
from supercog.engine.tools.salesforce               import SalesforceTool
from supercog.engine.tools.salesforce_dev_tool      import SalesforceDevTool
from supercog.engine.tools.sample_data_tool         import SampleDataTool
from supercog.engine.tools.scaleserp_browser        import ScaleSerpBrowserTool
from supercog.engine.tools.servicenow_tool          import ServiceNowCustomTool
from supercog.engine.tools.slack_tool               import SlackTool, SlackAppSlackTool
from supercog.engine.tools.sms_tool                 import SMSTool
from supercog.engine.tools.snowflake_tool           import SnowflakeTool
from supercog.engine.tools.speech_to_text           import SpeechToTextTool
from supercog.engine.tools.swagger_tool             import SwaggerTool
from supercog.engine.tools.tavily_search_tool       import TavilySearchTool
from supercog.engine.tools.text_to_speech_tool      import TextToSpeechTool
from supercog.engine.tools.website_docs             import WebsiteDocSource
from supercog.engine.tools.weather_tool             import WeatherTool
from supercog.engine.tools.yt_transcription_tool    import YouTubeTranscriptionTool
from supercog.engine.tools.zap_tool                 import ZapTool
from supercog.engine.tools.zapier_tool              import ZapierTool
from supercog.engine.tools.zyte                     import ZyteScraperTool
from supercog.engine.tools.zyte_screenshot          import ZyteScreenshotTool
from supercog.engine.tools.swagger_tool             import SwaggerTool
from supercog.engine.tools.yt_transcription_tool    import YouTubeTranscriptionTool
from supercog.engine.tools.discord_tool             import DiscordTool
from supercog.engine.tools.pdf_tool                 import PDFTool
from supercog.engine.tools.ragie_tool               import RagieTool
from supercog.engine.tools.google_drive             import GoogleDriveDocSource


TOOL_FACTORIES: list[ToolFactory] = [
    AdminTool(),
    AuthorizedRESTAPITool(),
    AutoDynamicTools(),
    BasicEmailerTool(),
    CalDAVTool(),
    CSVTool(),
    CodeInterpreterTool(),
    DatabaseTool(),
    DiscordTool(),
    DynamicAgentTool(),
    DuckdbTool(),
    EmotionLogicTool(),
    ExcelTool(),
    FileDownloadTool(),
    FTPTool(),
    # GmailAPITool(),
    GitTool(),
    # GoogleDocsTool(),
    GoogleCalendarTool(),
    GoogleNewsTool(),
    HubspotCRMTool(),
    IMAPTool(),
    ImageAnalysisTool(),
    ImageGeneratorTool(),
    JIRATool(),
    LinkedinDataTool(),
    LocalFolderDocSource(),
    MappingTool(),
    MatplotlibChartTool(),
    MemoryCompressionTool(),
    NmapTool(),
    NotionDocSource(),
    PandasTool(),
    PDFTool(),
    PlaywrightTool(),
    RAGTool(),
    # RESTAPITool(),
    RESTAPIToolV2(),
    ReadFileTool(),
    # ReflectionTool(),
    S3Tool(),
    SalesforceTool(),
    SalesforceDevTool(),
    SampleDataTool(),
    ScaleSerpBrowserTool(),
    ServiceNowCustomTool(),
    SlackTool(),
    SMSTool(),
    SnowflakeTool(),
    SpeechToTextTool(),
    SwaggerTool(),
    TavilySearchTool(),
    TextToSpeechTool(),
    WebsiteDocSource(),
    WeatherTool(),
    YouTubeTranscriptionTool(),
    ZapTool(),
    ZapierTool(),
    ZyteScraperTool(),
    ZyteScreenshotTool(),
    RagieTool(),
    GoogleDriveDocSource(),
] 

SLACK_TOOL_FACTORIES: list[ToolFactory] = [
    AutoDynamicTools(),
    BasicEmailerTool(),
    CSVTool(),
    DatabaseTool(),
    DiscordTool(),
    DuckdbTool(),
    ExcelTool(),
    FileDownloadTool(),
    FTPTool(),
    # GmailAPITool(),
    GitTool(),
    # GoogleDocsTool(),
    GoogleNewsTool(),
    HubspotCRMTool(),
    IMAPTool(),
    ImageAnalysisTool(),
    ImageGeneratorTool(),
    JIRATool(),
    LinkedinDataTool(),
    LocalFolderDocSource(),
    MatplotlibChartTool(),
    NotionDocSource(),
    PDFTool(),
#    RAGTool(),
    RagieTool(),
    RESTAPIToolV2(),
    ReadFileTool(),
    S3Tool(),
    SalesforceTool(),
    SampleDataTool(),
    ServiceNowCustomTool(),
    SlackAppSlackTool(),
    SMSTool(),
    SnowflakeTool(),
    SpeechToTextTool(),
    TavilySearchTool(),
    TextToSpeechTool(),
    WeatherTool(),
    YouTubeTranscriptionTool(),
    ZyteScraperTool(),
    ZyteScreenshotTool(),
] 


if os.environ.get("SPECIAL_TOOLS"):
    from supercog.engine.tools.native_interpreter import NativeInterpreterTool
    from supercog.engine.tools.dynamic_tool_builder import DynamicToolBuilder
    TOOL_FACTORIES.extend([NativeInterpreterTool(), DynamicToolBuilder()])

FACTORY_MAP: dict[str, ToolFactory] = {tf.id: tf for tf in TOOL_FACTORIES + SLACK_TOOL_FACTORIES}
TOOL_REGISTRY.load_registry_from_filesystem()
