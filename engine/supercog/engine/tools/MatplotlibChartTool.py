from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config
from supercog.shared.utils import upload_file_to_s3
from supercog.engine.tools.s3_utils import public_image_bucket
from typing import List, Callable, Dict, Any, Optional, Union
import json
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import io
from PIL import Image
import uuid
import numpy as np
import pandas as pd

class MatplotlibChartTool(ToolFactory):
    def __init__(self):
        super().__init__(
            id="matplotlib_chart_connector",
            system_name="Charting",
            logo_url="https://logo.clearbit.com/matplotlib.org",
            category=ToolCategory.CATEGORY_DEVTOOLS,
            help="""
Use this tool to create various types of charts using Matplotlib
""",
            auth_config={}
        )

    def get_tools(self) -> List[Callable]:
        return self.wrap_tool_functions([
            self.create_scatter_plot,
            self.create_bar_chart,
            self.create_line_chart,
            self.create_pie_chart,
            self.create_histogram,
            self.create_dataframe_chart,
        ])

    async def _process_and_upload_chart(
        self,
        fig,
        title: str,
        xlabel: str,
        ylabel: str,
        legend: bool = False,
        grid: bool = False
    ) -> Dict[str, str]:
        fig.suptitle(title)
        plt.xlabel(xlabel)
        plt.ylabel(ylabel)
        if legend:
            plt.legend()
        if grid:
            plt.grid(True)
        plt.tight_layout()
        img_buffer = io.BytesIO()
        fig.savefig(img_buffer, format='png', dpi=300)
        img_buffer.seek(0)
        object_name = f"images/{uuid.uuid4()}.png"
        public_url = upload_file_to_s3(
            img_buffer, 
            public_image_bucket(), 
            object_name, 
            mime_type="image/png"
        )
        plt.close(fig)
        return {
            "thumb": f"![Generated Chart]({public_url})"
        }

    async def create_scatter_plot(
        self,
        x: List[Any],
        y: List[Any],
        title: str,
        xlabel: str,
        ylabel: str,
        color: Union[str, List[str]] = 'blue',
        size: Union[float, List[float]] = 20,
        alpha: float = 1.0,
        marker: str = 'o',
        labels: Optional[List[str]] = None,
        legend: bool = False,
        grid: bool = False
    ) -> Dict[str, str]:
        """
        Creates a highly configurable scatter plot using Matplotlib.

        :param x: List of x-values
        :param y: List of y-values
        :param title: Title of the chart
        :param xlabel: Label for x-axis
        :param ylabel: Label for y-axis
        :param color: Color(s) of the markers. Can be a single color or a list of colors.
        :param size: Size(s) of the markers. Can be a single size or a list of sizes.
        :param alpha: Transparency of the markers (0.0 to 1.0)
        :param marker: Marker style (e.g., 'o', 's', '^', 'D', etc.)
        :param labels: Labels for each point (for legend)
        :param legend: Whether to show the legend
        :param grid: Whether to show the grid
        :return: A dictionary containing the markdown-formatted image link
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        scatter = ax.scatter(x, y, c=color, s=size, alpha=alpha, marker=marker)
        if labels:
            for i, label in enumerate(labels):
                ax.annotate(label, (x[i], y[i]))
        return await self._process_and_upload_chart(
            fig,
            title,
            xlabel,
            ylabel,
            legend,
            grid
        )

    async def create_bar_chart(
        self,
        x: List[Any],
        y: List[Any],
        title: str,
        xlabel: str = "",
        ylabel: str = "",
        orientation: str = 'v',
        color: Union[str, List[str]] = 'blue',
        label_rotation: float = 45,
        bar_width: float = 0.8,
        error_bars: Optional[List[float]] = None,
        legend: bool = False,
        grid: bool = False
    ) -> Dict[str, str]:
        """
        Creates a highly configurable bar chart using Matplotlib.

        :param x: List of x-values (categories for vertical bars, values for horizontal bars)
        :param y: List of y-values (values for vertical bars, categories for horizontal bars)
        :param title: Title of the chart
        :param xlabel: Label for x-axis
        :param ylabel: Label for y-axis
        :param orientation: 'v' for vertical bars, 'h' for horizontal bars
        :param color: Color(s) of the bars. Can be a single color or a list of colors.
        :param label_rotation: Rotation angle for x-axis labels (in degrees)
        :param bar_width: Width of the bars
        :param error_bars: List of error bar values
        :param legend: Whether to show the legend
        :param grid: Whether to show the grid
        :return: A dictionary containing the markdown-formatted image link
        """
        print(f"Creating bar chart with {len(x)} items, orientation: {orientation}, label_rotation: {label_rotation}")
        print(f"Colors: {color[:5]}... (showing first 5)")

        fig, ax = plt.subplots(figsize=(15, 10))  # Increased figure size for better readability
        
        if orientation == 'h':
            bars = ax.barh(range(len(y)), x, height=bar_width, color=color, xerr=error_bars)
            ax.set_yticks(range(len(y)))
            ax.set_yticklabels(y, rotation=0)  # No rotation for horizontal bars
            ax.invert_yaxis()  # Invert y-axis to show first president at the top
        else:
            bars = ax.bar(range(len(x)), y, width=bar_width, color=color, yerr=error_bars)
            ax.set_xticks(range(len(x)))
            ax.set_xticklabels(x, rotation=label_rotation, ha='right')  # Align labels to the right

        # Add value labels on the bars
        for bar in bars:
            if orientation == 'h':
                width = bar.get_width()
                ax.text(width, bar.get_y() + bar.get_height()/2, f'{width:.1f}', 
                        ha='left', va='center')
            else:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2, height, f'{height:.1f}', 
                        ha='center', va='bottom')

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        if grid:
            ax.grid(axis='y' if orientation == 'h' else 'x', linestyle='--', alpha=0.7)

        plt.tight_layout()  # Adjust layout to prevent clipping of labels

        print("Bar chart created successfully")
        return await self._process_and_upload_chart(
            fig,
            title,
            xlabel,
            ylabel,
            legend,
            grid
        )

    async def create_line_chart(
        self,
        x: List[Any],
        y: Union[List[Any], List[List[Any]]],
        title: str,
        xlabel: str,
        ylabel: str,
        colors: Union[str, List[str]] = 'blue',
        styles: Union[str, List[str]] = '-',
        markers: Union[str, List[str]] = '',
        linewidths: Union[float, List[float]] = 2,
        labels: Optional[List[str]] = None,
        legend: bool = True,
        grid: bool = True
    ) -> Dict[str, str]:
        """
        Creates a highly configurable line chart using Matplotlib.

        :param x: List of x-values
        :param y: List of y-values or list of lists for multiple lines
        :param title: Title of the chart
        :param xlabel: Label for x-axis
        :param ylabel: Label for y-axis
        :param colors: Color(s) of the lines. Can be a single color or a list of colors.
        :param styles: Line style(s). Can be a single style or a list of styles.
        :param markers: Marker style(s). Can be a single style or a list of styles.
        :param linewidths: Line width(s). Can be a single width or a list of widths.
        :param labels: Labels for each line (for legend)
        :param legend: Whether to show the legend
        :param grid: Whether to show the grid
        :return: A dictionary containing the markdown-formatted image link
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        
        if not isinstance(y[0], list):
            y = [y]
        
        if isinstance(colors, str):
            colors = [colors] * len(y)
        if isinstance(styles, str):
            styles = [styles] * len(y)
        if isinstance(markers, str):
            markers = [markers] * len(y)
        if isinstance(linewidths, (int, float)):
            linewidths = [linewidths] * len(y)
        
        for i, y_data in enumerate(y):
            ax.plot(x, y_data, color=colors[i], linestyle=styles[i], marker=markers[i], 
                    linewidth=linewidths[i], label=labels[i] if labels else None)
        
        return await self._process_and_upload_chart(
            fig,
            title,
            xlabel,
            ylabel,
            legend,
            grid
        )

    async def create_pie_chart(
        self,
        labels: List[str],
        values: List[float],
        title: str,
        colors: Optional[List[str]] = None,
        explode: Optional[List[float]] = None,
        autopct: str = '%1.1f%%',
        startangle: float = 0,
        shadow: bool = False,
        legend: bool = True
    ) -> Dict[str, str]:
        """
        Creates a highly configurable pie chart using Matplotlib.

        :param labels: List of labels for pie chart sectors
        :param values: List of values corresponding to labels
        :param title: Title of the chart
        :param colors: List of colors for each sector
        :param explode: List of float values to "explode" each sector away from the center
        :param autopct: String format for sector values
        :param startangle: Starting angle for the first sector
        :param shadow: Whether to draw a shadow beneath the pie
        :param legend: Whether to show the legend
        :return: A dictionary containing the markdown-formatted image link
        """
        fig, ax = plt.subplots(figsize=(10, 8))
        ax.pie(values, labels=labels, colors=colors, explode=explode, autopct=autopct,
               startangle=startangle, shadow=shadow)
        ax.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle
        return await self._process_and_upload_chart(
            fig,
            title,
            "",
            "",
            legend,
            False
        )

    async def create_histogram(
        self,
        x: List[Any],
        title: str,
        xlabel: str,
        ylabel: str,
        bins: Union[int, List[float], str] = 10,
        color: str = 'blue',
        edgecolor: str = 'black',
        alpha: float = 0.7,
        density: bool = False,
        cumulative: bool = False,
        legend: bool = False,
        grid: bool = True
    ) -> Dict[str, str]:
        """
        Creates a highly configurable histogram using Matplotlib.

        :param x: List of values to bin
        :param title: Title of the chart
        :param xlabel: Label for x-axis
        :param ylabel: Label for y-axis
        :param bins: Number of bins, list of bin edges, or binning strategy (e.g., 'auto', 'sturges')
        :param color: Color of the bars
        :param edgecolor: Color of the bar edges
        :param alpha: Transparency of the bars (0.0 to 1.0)
        :param density: If True, draw and return a probability density
        :param cumulative: If True, draw a cumulative histogram
        :param legend: Whether to show the legend
        :param grid: Whether to show the grid
        :return: A dictionary containing the markdown-formatted image link
        """
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.hist(x, bins=bins, color=color, edgecolor=edgecolor, alpha=alpha, 
                density=density, cumulative=cumulative)
        return await self._process_and_upload_chart(
            fig,
            title,
            xlabel,
            ylabel,
            legend,
            grid
        )

    async def create_dataframe_chart(
        self,
        dataframe_var: str,
        title: str,
        xlabel: str,
        ylabel: str,
        chart_type: str = 'bar',
        stacked: bool = False,
        figsize: tuple = (12, 6),
        colors: Optional[List[str]] = None,
        legend: bool = True,
        grid: bool = True,
        rotation: int = 45
    ) -> Dict[str, str]:
        """
        Creates a chart from a DataFrame using Matplotlib.

        :param dataframe_var: Name of the DataFrame variable
        :param title: Title of the chart
        :param xlabel: Label for x-axis
        :param ylabel: Label for y-axis
        :param chart_type: Type of chart to create ('bar', 'line', or 'area')
        :param stacked: Whether to stack the data (for bar and area charts)
        :param figsize: Size of the figure (width, height)
        :param colors: List of colors for the chart elements
        :param legend: Whether to show the legend
        :param grid: Whether to show the grid
        :param rotation: Rotation angle for x-axis labels
        :return: A dictionary containing the markdown-formatted image link
        """
        # Retrieve the DataFrame using the superclass method
        df, df_name = self.get_dataframe_from_handle(dataframe_var)

        fig, ax = plt.subplots(figsize=figsize)

        if chart_type == 'bar':
            df.plot(kind='bar', ax=ax, stacked=stacked, color=colors)
        elif chart_type == 'line':
            df.plot(kind='line', ax=ax, color=colors)
        elif chart_type == 'area':
            df.plot(kind='area', ax=ax, stacked=stacked, color=colors)
        else:
            raise ValueError(f"Unsupported chart type: {chart_type}")

        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        
        if legend:
            ax.legend(title="Columns")
        
        if grid:
            ax.grid(True, linestyle='--', alpha=0.7)
        
        plt.xticks(rotation=rotation)
        plt.tight_layout()

        return await self._process_and_upload_chart(
            fig,
            title,
            xlabel,
            ylabel,
            legend,
            grid
        )
