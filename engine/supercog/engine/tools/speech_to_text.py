from supercog.engine.tool_factory import ToolFactory, ToolCategory, TOOL_REGISTRY
from supercog.shared.services     import config
from supercog.engine.filesystem   import unrestricted_filesystem
from supercog.shared.logging      import logger
from supercog.engine.db           import session_context
from supercog.shared.services     import config, db_connect
#from supercog.shared.apubsub      import AudioStreamEvent

from sqlmodel                     import Session

from pydub                        import AudioSegment
from pydub.playback               import play
from io                           import BytesIO
from openai                       import OpenAI
from datetime                     import datetime
from typing                       import List, Callable, Optional
#import sounddevice                as sd
import numpy                      as np
import scipy.io.wavfile           as wav

import asyncio
import httpx
import json
import os
import io
import re
import traceback
import math

class SpeechToTextTool(ToolFactory):
    openai_api_key:str = "sk-proj-PDI78VjJBwpk2mTDjeorT3BlbkFJVt1lST4qeAxdnriasH1y"
    tenant_id:str = ""
    run_id:str = ""
    
    def __init__(self):
        super().__init__(
            id="speech_to_text_connector",
            system_name="Speech to Text",
            logo_url="https://logo.clearbit.com/openai.com",
            auth_config = {},
            category=ToolCategory.CATEGORY_SPEECH,
            help="""
Use this tool to convert speech to text using OpenAI's Whisper API
""",
        )


    def get_tools(self) -> List[Callable]:
        """
        Retrieves the OpenAI API key and wraps the tool functions
        :param secrets: A dictionary containing secrets, which may include the OpenAI API key.
        :return: A list of callable functions that the tool provides.
        """
        #if secrets:
        #    self.openai_api_key = secrets.get('openai_api_key', '')
        #    #print("------> The _meta has: ",dir(secrets['_meta'])) 
        #    self.tenant_id      = secrets['_meta'].tenant_id
        #    self.run_id         = secrets['_meta'].run_id
        self.openai_api_key=config.get_global("OPENAI_API_KEY")
        return self.wrap_tool_functions([
            self.generate_text_from_microphone,
            self.generate_text_from_file,
            self.local_playback_from_file,
            self.playback_from_file_to_file,
            self.extract_from_file_to_file,
        ])

    def _local_play_back(self, byte_io_wav):
        """
        Plays back audio using pydub from a WAV byte stream.
        """
        with unrestricted_filesystem():
            # Load the MP3 data into an AudioSegment and play it
            audio_segment_wav = AudioSegment.from_file(byte_io_wav, format="wav")
            play(audio_segment_wav)
            
    def _extract_wav_from_file(self, file_name: str,
                               start_pos_in_secs: int,
                               end_pos_in_secs: int,
                               language="en"):
        """
        Reads audio from a file, slices it according to start and end positions, converts to WAV format,.

        Args:
            file_name: The path to the audio file.
            start_pos_in_secs: Start position of the playback in seconds.
            end_pos_in_secs: End position of the playback in seconds.
            language: The language of the audio to transcribe (default: "en").

        Returns:
            wave BytesIo object.
        """
        # Load the audio file
        audio_segment = AudioSegment.from_file(file_name)

        # Calculate start and end times in milliseconds
        start_ms = start_pos_in_secs * 1000
        end_ms = end_pos_in_secs * 1000

        # Slice the audio from start_pos to end_pos
        play_segment = audio_segment[start_ms:end_ms]

        # Export the sliced audio to a BytesIO object in WAV format
        byte_io_wav = BytesIO()
        play_segment.export(byte_io_wav, format="wav")
        byte_io_wav.seek(0)
        return(byte_io_wav)


    def local_playback_from_file(self,
                                 file_name: str,
                                 start_pos_in_secs: int,
                                 end_pos_in_secs: int,
                                 language="en"):
        """
        Reads audio from a file, slices it according to start and end positions, converts to WAV format,
        and plays the segment.

        Args:
            file_name: The path to the audio file.
            start_pos_in_secs: Start position of the playback in seconds.
            end_pos_in_secs: End position of the playback in seconds.
            language: The language of the audio to transcribe (default: "en").

        Returns:
            None. Plays audio segment from start_pos_in_secs to end_pos_in_secs.
        """
        byte_io_wav = self._extract_wav_from_file(file_name,
                                                  start_pos_in_secs,
                                                  end_pos_in_secs,
                                                  language)
        # play back the audio
        return self._local_play_back(byte_io_wav)

    def extract_from_file_to_file(self,
                                  speech_input_file_name: str,
                                  start_pos_in_secs: int,
                                  end_pos_in_secs: int,
                                  language="en"):
        """
        Reads audio from a file, slices it according to start and end positions, converts to WAV format,
        and creates a file on s3 from the segment. Instead of returning a playback json string we just
        return the audio filename

        Args:
            speech_input_file_name: The path to the audio file.
            start_pos_in_secs: Start position of the playback in seconds.
            end_pos_in_secs: End position of the playback in seconds.
            language: The language of the audio to transcribe (default: "en").

        Returns:
            None. Plays audio segment from start_pos_in_secs to end_pos_in_secs.
        """
        byte_io_wav = self._extract_wav_from_file(speech_input_file_name,
                                                  start_pos_in_secs,
                                                  end_pos_in_secs,
                                                  language)
        filename, save_path = self._unique_file_name("real_voices",
                                                     speech_input_file_name,
                                                     start_pos_in_secs,
                                                     end_pos_in_secs)
        file_info = self._save_audio_to_s3(byte_io_wav, filename, save_path)
        data = json.loads(file_info)
        audio_url = data.get("audio_url")
        return json.dumps({
            "audio_url": audio_url
        })
    
    async def playback_from_file_to_file(self,
                                         speech_input_file_name: str,
                                         start_pos_in_secs: int,
                                         end_pos_in_secs: int,
                                         language="en"):
                                         #callbacks: LangChainCallback):
        """
        Reads audio from a file, slices it according to start and end positions, converts to WAV format,
        and creates a file on s3 from the segment.

        Args:
            speech_input_file_name: The path to the audio file.
            start_pos_in_secs: Start position of the playback in seconds.
            end_pos_in_secs: End position of the playback in seconds.
            language: The language of the audio to transcribe (default: "en").

        Returns:
            None. Plays audio segment from start_pos_in_secs to end_pos_in_secs.
        """
        byte_io_wav = self._extract_wav_from_file(speech_input_file_name,
                                                  start_pos_in_secs,
                                                  end_pos_in_secs,
                                                  language)

        filename, save_path = self._unique_file_name("real_voices",
                                                     speech_input_file_name,
                                                     start_pos_in_secs,
                                                     end_pos_in_secs)
        file_info = self._save_audio_to_s3(byte_io_wav, filename, save_path)
        return file_info
        #await self.run_context.publish(
        #    self.run_context.create_event(AudioStreamEvent, callbacks, audio_url = file_info.audio_url)
        #)

    def _unique_file_name(self, voice: str, filename: str, start_pos, end_pos) -> str:
        # Generate a unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{filename}_{voice}_{start_pos}_{end_pos}_{timestamp}.mp3"
        # Define the path where the file will be saved
        save_path = os.path.join("audio", filename)
        print(f"Audio file path: {save_path}")

        # Ensure the directory exists
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        return filename, save_path
    
    def _save_audio_to_s3(self, audio_data, filename, save_path) -> str:
        """
        Save audio data to a local file and then upload it to an S3 bucket.

        Args:
            voice (str): The voice identifier used to generate the filename.
            audio_data: The raw audio data to be saved and uploaded. It can
            be a bytes-like object or an _io.BytesIO object.

        Returns:
            str: A JSON string containing either the audio URL or an error message.

        Raises:
            ValueError: If the created file is empty.
            FileNotFoundError: If the file does not exist after an attempted write.
        """
        try:
            # Convert _io.BytesIO object to raw bytes if necessary
            if isinstance(audio_data, bytes):
                raw_data = audio_data
            else:
                raw_data = audio_data.read()

            # Write the raw audio data directly to file
            with open(save_path, 'wb') as f:
                f.write(raw_data)

            # Verify file existence and size
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                print(f"File exists. Size: {file_size} bytes")

                # Upload to S3
                raw_url = self.run_context.upload_user_file_to_s3(
                    file_name=filename,
                    original_folder="audio",
                    mime_type="audio/mpeg"
                )
                print(f"generate_speech_file_from_text: Speech saved successfully: Raw_url -> {raw_url}")
                # Get the correct URL
                audio_url = self.run_context.get_file_url(filename, "audio")
                print(f"generate_speech_file_from_text: correct URL -> {audio_url}")

                # Clean up the local file after successful upload
                #os.remove(save_path)
                #print(f"generate_speech_file_from_text: Local file removed -> {save_path}")

                # Return the URL as a JSON string
                return_string =  json.dumps({
                    "content_type": "audio/mpeg",
                    "audio_url": audio_url.get("url")
                })
                #print(f"_save_audio_to_s3: return string = {return_string}")

                return return_string
            else:
                raise FileNotFoundError(f"File does not exist after attempted write: {save_path}")
        except Exception as e:
            error_message = f"Error saving audio file to s3: {str(e)}"
            print(error_message)
            return json.dumps({"error": error_message})
            
    def _split_audio(self, byte_io_wav, chunk_length=60):
        """
        Splits the audio file into chunks of specified length in seconds.
        Args:
            byte_io_wav: BytesIO object containing WAV audio.
            chunk_length: Length of each audio chunk in seconds (default is 60 seconds).
        Returns:
            A list of BytesIO objects each containing a chunk of the original audio.
        """
        byte_io_wav.seek(0)
        audio = AudioSegment.from_wav(byte_io_wav)
        chunks = []

        for i in range(0, len(audio), chunk_length * 1000):
            chunk = audio[i:i + chunk_length * 1000]
            chunk_byte_io = BytesIO()
            chunk.export(chunk_byte_io, format="wav")
            chunk_byte_io.seek(0)
            chunks.append(chunk_byte_io)

        return chunks
        
    def _transcribe(self, byte_io_wav, language) -> str :
        """
        Transcribes audio from a WAV byte stream using OpenAI's Whisper API.
        """
        client = OpenAI(api_key=self.openai_api_key) # Initialize OpenAI client

        byte_io_wav.seek(0)
        byte_io_wav.name = "file.wav"  # this is the important line
        translation = client.audio.transcriptions.create(
            model="whisper-1",
            file=("temp." + "wav", byte_io_wav, "audio/wav"),
            language=language
        )
        return translation.text
    

    def _transcribe_chunks(self, byte_io_wav,
                           language: str = "en",
                           response_format: str = "json",
                           start_pos_in_secs: Optional[float] = None,
                           end_pos_in_secs: Optional[float] = None):
        """
        Transcribes a specified segment of the audio file using OpenAI's Whisper API.
        Args:
            byte_io_wav: BytesIO object containing WAV audio.
            language: The language of the audio to transcribe (default: "en").
            response_format: The format of the response (default: "json").
            start_pos_in_secs: Optional start position in seconds from which to start transcription.
            end_pos_in_secs: Optional end position in seconds at which to stop transcription.
        Returns:
            A list of strings, each string is the transcription of a part of the audio.
        """
        # Split the audio into 60-second chunks
        chunks = self._split_audio(byte_io_wav)

        # Calculate the chunk indices for start and end positions
        start_chunk_index = math.floor(start_pos_in_secs / 60) if start_pos_in_secs is not None else 0
        end_chunk_index = math.ceil(end_pos_in_secs / 60) if end_pos_in_secs is not None else len(chunks) - 1

        # Ensure end_chunk_index is within bounds
        end_chunk_index = min(end_chunk_index, len(chunks) - 1)

        transcriptions = []
        client = OpenAI(api_key=self.openai_api_key)  # Initialize OpenAI client

        # Process each chunk within the start and end range
        for i in range(start_chunk_index, end_chunk_index + 1):
            if i >= len(chunks):
                break  # Exit the loop if we've reached the end of available chunks

            chunks[i].seek(0)  # Reset to the start of the chunk

            # Transcribe the current chunk
            chunks[i].name = f"chunk_{i}.wav"  # This might be required by some APIs
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=("temp.wav", chunks[i], "audio/wav"),
                language=language,
                response_format=response_format
            )

            # Handle the response based on the specified format
            if response_format == "json":
                transcriptions.append(transcript.text)
            elif response_format in ["text", "srt", "vtt"]:
                transcriptions.append(transcript)
            elif response_format == "verbose_json":
                transcriptions.append(transcript.text)
            else:
                raise ValueError(f"Unsupported response format: {response_format}")

        return transcriptions

    def generate_text_from_file(self,
                                file_name: str,
                                start_pos_in_secs: Optional[float] = None,
                                end_pos_in_secs: Optional[float] = None,
                                language: str = "en",
                                page_length: int = 60,
                                response_format: str = "text"):
        """
        Reads audio from a file and transcribes it to text using OpenAI's Whisper API.
        Args:
            file_name: The path to the audio file.
            start_pos_in_secs: Optional start position in seconds (default: None, start from beginning).
            end_pos_in_secs: Optional end position in seconds (default: None, process until end of file).
            language: The language of the audio to transcribe (default: "en").
            page_length: The maximum number of characters per line in the formatted output (default: 60).
            response_format: The format of the response (default: "text").

        Returns:
            A string containing the transcribed text, formatted according to the specified parameters.
        """
        try:
            # Load the audio file into a byte stream
            audio_segment = AudioSegment.from_file(file_name)

            # Convert start and end positions to float if they're not None
            start_pos_in_secs = float(start_pos_in_secs) if start_pos_in_secs is not None else 0
            end_pos_in_secs = float(end_pos_in_secs) if end_pos_in_secs is not None else None

            # If end_pos_in_secs is not specified or exceeds the file duration, set it to the file duration
            if end_pos_in_secs is None or end_pos_in_secs > (len(audio_segment) / 1000):
                end_pos_in_secs = len(audio_segment) / 1000

            # Export the audio to a BytesIO object in WAV format for consistency
            byte_io_wav = BytesIO()
            audio_segment.export(byte_io_wav, format="wav")
            byte_io_wav.seek(0)

            # Transcribe the audio
            transcribed_result = self._transcribe_chunks(byte_io_wav,
                                                         language,
                                                         response_format,
                                                         start_pos_in_secs,
                                                         end_pos_in_secs)

            if response_format != "text":
                return transcribed_result

            # Check if the result is a list and convert it to a string
            if isinstance(transcribed_result, list):
                transcribed_text = ' '.join(transcribed_result)
            elif isinstance(transcribed_result, str):
                transcribed_text = transcribed_result
            else:
                raise ValueError(f"Expected a string or list, but got {type(transcribed_result)}")

            # Format the transcribed text into pages
            formatted_text = self.turn_long_text_to_pages(transcribed_text, page_length)

            return formatted_text

        except Exception as e:
            logger.error(f"Error in generate_text_from_file: {str(e)}")
            return f"Error: {str(e)}"

    def generate_text_from_microphone(self, duration=5, language="en"):
        """
        Records audio from the microphone and transcribes it to text using OpenAI's Whisper API.
        Args:
            duration: The duration in seconds for which to record audio (default: 5).
            language: The language of the audio to transcribe (default: "en").
        Returns:
            A string containing the transcribed text.
        """
        byte_io_wav = self._local_capture_microphone(duration)
        self.play_back(byte_io_wav)     
        return self.transcribe(byte_io_wav, language)

        
    def turn_long_text_to_pages(self, text: str, n: int) -> str:
        """
        Splits a long string into lines, ensuring that no line exceeds n characters,
        and that lines are split at whitespace where possible.

        Args:
            text (str): The input string to be split.
            n (int): The maximum number of characters per line.

        Returns:
            str: The formatted string with newlines inserted at appropriate positions.
        """
        # Split the text into words
        words = re.findall(r'\S+|\s+', text)

        lines = []
        current_line = ""

        for word in words:
            # Check if adding the word exceeds the line length
            if len(current_line) + len(word) > n:
                # Append the current line to lines
                lines.append(current_line.strip())
                # Start a new line with the current word
                current_line = word
            else:
                # Add the word to the current line
                current_line += word

        # Append any remaining text in current_line to lines
        if current_line:
            lines.append(current_line.strip())

        # Join the lines with newline characters
        formatted_text = '\n'.join(lines)

        return formatted_text

