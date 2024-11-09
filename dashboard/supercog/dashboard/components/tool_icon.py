import reflex as rx

class ToolIcon(rx.Component):
	icon_library: rx.Var[str]
	size: rx.Var[int | None]

	def add_imports(self):
		return {f"react-icons/{self.icon_library}": [rx.ImportVar(install=False, tag=self.tag)]}

def tool_icon(tool_id: str, agent_url: str = "", logo_url: str = "", tool_size: int = 16) -> rx.Component:
    return rx.box(
		rx.cond(
			(agent_url != "") & (logo_url != ""),
			rx.chakra.image(
				src=logo_url,
				width=f"{tool_size}px",
				height=f"{tool_size}px",
			),
			rx.match(
				tool_id,
				("admin_connector", ToolIcon(icon_library="tb", tag="TbShieldHalfFilled", size=tool_size)),
				("agent_tool", ToolIcon(icon_library="tb", tag="TbRobotFace", size=tool_size)),
				("auth_rest_api_tool", ToolIcon(icon_library="tb", tag="TbShieldCheck", size=tool_size)),
				("basic_data_functions", ToolIcon(icon_library="tb", tag="TbBrackets", size=tool_size)),
				("basic_emailer", ToolIcon(icon_library="tb", tag="TbMail", size=tool_size)),
				("code_interpreter_tool", ToolIcon(icon_library="tb", tag="TbCode", size=tool_size)),
				("code_introspection_connector", ToolIcon(icon_library="tb", tag="TbListSearch", size=tool_size)),
				("csv_connector", ToolIcon(icon_library="tb", tag="TbFileTypeCsv", size=tool_size)),
				("database", ToolIcon(icon_library="tb", tag="TbDatabase", size=tool_size)),
				("discord", ToolIcon(icon_library="si", tag="SiDiscord", size=tool_size)),
				("duckdb_tool", ToolIcon(icon_library="si", tag="SiDuckdb", size=tool_size)),
				("dynamic_agent_tools", ToolIcon(icon_library="tb", tag="TbBolt", size=tool_size)),
				("dynamic_tool_builder_connector", ToolIcon(icon_library="tb", tag="TbTools", size=tool_size)),
				("emotion_logic", ToolIcon(icon_library="tb", tag="TbMoodSmile", size=tool_size)),
				("excel_connector", ToolIcon(icon_library="si", tag="SiMicrosoftexcel", size=tool_size)),
				("file_download", ToolIcon(icon_library="tb", tag="TbDownload", size=tool_size)),
				("ftp_connector", ToolIcon(icon_library="tb", tag="TbFolderOpen", size=tool_size)),
				("git_connector", ToolIcon(icon_library="si", tag="SiGithub", size=tool_size)),
				("gmailapi_connector", ToolIcon(icon_library="si", tag="SiGmail", size=tool_size)),
				("google_docs_connector", ToolIcon(icon_library="si", tag="SiGoogledocs", size=tool_size)),
				("google_news_connector", ToolIcon(icon_library="si", tag="SiGooglenews", size=tool_size)),
				("hubspot_crm_tool", ToolIcon(icon_library="si", tag="SiHubspot", size=tool_size)),
				("image_analysis", ToolIcon(icon_library="tb", tag="TbPhotoSearch", size=tool_size)),
				("image_generator", ToolIcon(icon_library="tb", tag="TbSparkles", size=tool_size)),
				("imap_connector", ToolIcon(icon_library="si", tag="SiGmail", size=tool_size)),
				("jira_connector", ToolIcon(icon_library="si", tag="SiAtlassian", size=tool_size)),
				("mapping_connector", ToolIcon(icon_library="tb", tag="TbMap", size=tool_size)),
				("matplotlib_chart_connector", ToolIcon(icon_library="tb", tag="TbChartDots", size=tool_size)),
				("memory_compression_tool_id", ToolIcon(icon_library="tb", tag="TbStackPush", size=tool_size)),
				("native_interpreter_tool", ToolIcon(icon_library="tb", tag="TbSandbox", size=tool_size)),
				("nmap_connector", ToolIcon(icon_library="tb", tag="TbEye", size=tool_size)),
				("pandas_tools", ToolIcon(icon_library="si", tag="SiPandas", size=tool_size)),
				("pdf_tool", ToolIcon(icon_library="tb", tag="TbFileTypePdf", size=tool_size)),
				("playwright_connector", ToolIcon(icon_library="si", tag="SiPlaywright", size=tool_size)),
				("rag_tool", ToolIcon(icon_library="tb", tag="TbHierarchy", size=tool_size)),
				("read_file", ToolIcon(icon_library="tb", tag="TbUpload", size=tool_size)),
				("reflection", ToolIcon(icon_library="tb", tag="TbBubble", size=tool_size)),
				("rest_api_tool_v2", ToolIcon(icon_library="tb", tag="TbPlugConnected", size=tool_size)),
				("rest_api_tool", ToolIcon(icon_library="tb", tag="TbPlugConnected", size=tool_size)),
				("s3_connector", ToolIcon(icon_library="si", tag="SiAmazonwebservices", size=tool_size)),
				("salesforce", ToolIcon(icon_library="si", tag="SiSalesforce", size=tool_size)),
				("salesforce_dev", ToolIcon(icon_library="si", tag="SiSalesforce", size=tool_size)),
				("sample_data", ToolIcon(icon_library="tb", tag="TbTestPipe", size=tool_size)),
				("slack_connector", ToolIcon(icon_library="si", tag="SiSlack", size=tool_size)),
				("sms_connector", ToolIcon(icon_library="tb", tag="TbDeviceMobileMessage", size=tool_size)),
				("snowflake_connector", ToolIcon(icon_library="si", tag="SiSnowflake", size=tool_size)),
				("speech_to_text_connector", ToolIcon(icon_library="tb", tag="TbMicrophone", size=tool_size)),
				("swagger_tool", ToolIcon(icon_library="si", tag="SiSwagger", size=tool_size)),
				("tavily_search", ToolIcon(icon_library="tb", tag="TbWorldSearch", size=tool_size)),
				("text_to_speech_connector", ToolIcon(icon_library="tb", tag="TbSpeakerphone", size=tool_size)),
				("weather_connector", ToolIcon(icon_library="tb", tag="TbCloudStorm", size=tool_size)),
				("web_browser", ToolIcon(icon_library="tb", tag="TbBrowser", size=tool_size)),
				("youtube_transcription_tool", ToolIcon(icon_library="tb", tag="TbBrandYoutube", size=tool_size)),
				("zap_connector", ToolIcon(icon_library="si", tag="SiZap", size=tool_size)),
				("zapier_connector", ToolIcon(icon_library="si", tag="SiZapier", size=tool_size)),
				("zyte_scraping", ToolIcon(icon_library="si", tag="SiZyte", size=tool_size)),
				("zyte_screenshot", ToolIcon(icon_library="tb", tag="TbScreenshot", size=tool_size)),
				rx.cond(
					logo_url,
					rx.chakra.image(
						src=logo_url,
						width=f"{tool_size}px",
						height=f"{tool_size}px",
						filter="grayscale(1)",
					), # Default case is a grayscale image or a gear if no image
					ToolIcon(icon_library="tb", tag="TbSettings", size=tool_size),
				),
			),
		),
		width=f"{tool_size}px",
		height=f"{tool_size}px",
		display="flex",
		align_items="center"
	)
