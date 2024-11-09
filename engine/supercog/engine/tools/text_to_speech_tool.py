from supercog.engine.tool_factory import ToolFactory, ToolCategory
from supercog.shared.services import config
import openai
from openai import OpenAI
from pydub import AudioSegment
from pydub.playback import play
from io import BytesIO
from typing import List, Callable
import tempfile
import os
import numpy as np
import replicate
import asyncio
import httpx
import json
import time
#import sounddevice as sd
from supercog.engine.filesystem import unrestricted_filesystem
from datetime import datetime

class TextToSpeechTool(ToolFactory):
    openai_api_key: str = ""

    def __init__(self):
        super().__init__(
            id="text_to_speech_connector",
            system_name="Text to Speech",
            logo_url="https://logo.clearbit.com/openai.com",
            auth_config={
                #"strategy_token": {
                #    "openai_api_key": "API KEY - find this at https://platform.openai.com/api-keys",
                #    "help": "Create an OpenAI API key and set the value here."
                #}
            },
            category=ToolCategory.CATEGORY_SPEECH,
            help="""
Use this tool to convert text to speech using OpenAI's API
"""
        )

    def get_tools(self) -> List[Callable]:
        self.openai_api_key=config.get_global("OPENAI_API_KEY")
        import os
        os.environ["REPLICATE_API_TOKEN"] = "r8_IntogAytpwbunSdaup3OxKVS7kJv00W2jruYC"
        return self.wrap_tool_functions([
            #self.local_generate_speech_from_text,
            self.generate_speech_file_from_text,
            #self.bark_generate_speech_from_text,
            self.sleep_for,
        ])
    
    def sleep_for(self, seconds):
        """
        Sleep for the specified number of seconds. Used to pause while speech is being played

        Args:
        seconds (float): The number of seconds to sleep.
        """
        time.sleep(seconds)
        
    async def bark_generate_speech_from_text(self, text: str, voice: str = ""):
        """
        Generates speech audio from the given text using the Replicate API.

        This asynchronous function takes a text input and optionally a specific voice,
        sends a request to the Replicate API (specifically the Bark model), and 
        returns a JSON string containing the URL of the generated audio and its content type.

        Args:
            text (str): The text to be converted to speech.
            voice (str, optional): A string identifier for a specific voice to use. 
                                   If None, the default voice will be used. Defaults to None.

        Returns:
            str: A JSON string containing:
                 - 'content_type': The MIME type of the audio (default is "audio/mpeg")
                 - 'audio_url': The URL where the generated audio can be accessed
        """
        input_data = {"prompt": text}

        # If a specific voice is requested, add it to the input
        if voice:
            input_data["history_prompt"] = voice

        # Call Replicate API to generate audio
        output = replicate.run(
            #"suno-ai/bark:latest",
            "suno-ai/bark:b76242b40d67c76ab6742e987628a2a9ac019e11d56ab96c4e91ce03b79b2787",
            input=input_data
        )

        # Assuming the output is a URL to the generated audio
        audio_url = output.get("audio_out")

        # Construct the response dictionary
        response = {
            "content_type": "audio/mpeg",  # Adjust this if the content type is different
            "audio_url": audio_url
        }

        # Return the JSON string
        return json.dumps(response)

    def local_generate_speech_from_text(self, voice: str, text: str) -> str:
        """
        Generate speech from the given text using OpenAI's Text-to-Speech API.
        :param voice: str one of: alloy, echo, fable, onyx, nova, and shimmer
        :param text: str
            The text to be converted to speech.
        """
        try:
            client = OpenAI(api_key=self.openai_api_key)
            response = response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            audio_data = response.content
            with unrestricted_filesystem():
                audio_segment = AudioSegment.from_file(BytesIO(audio_data), format="mp3")
                play(audio_segment)
                print("Speech has been played successfully.")
        except Exception as e:
            return f"Error generating speech: {str(e)}"
        return "Success converting text to speech"

    def _save_audio_to_s3(self, voice: str, audio_data) -> str:
         """
         Save audio data to a local file and then upload it to an S3 bucket.

         Args:
             voice (str): The voice identifier used to generate the filename.
             audio_data: The raw audio data to be saved and uploaded.

         Returns:
             str: A JSON string containing either the audio URL or an error message.

         Raises:
             ValueError: If the created file is empty.
             FileNotFoundError: If the file does not exist after an attempted write.
         """
         try:
            # Generate a unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"speech_{voice}_{timestamp}.mp3"
            # Define the path where the file will be saved
            save_path = os.path.join("audio", filename)
            print(f"Audio file path: {save_path}")

            # Ensure the directory exists
            os.makedirs(os.path.dirname(save_path), exist_ok=True)

            # Write the raw audio data directly to file
            with open(save_path, 'wb') as f:
                f.write(audio_data)

            # Verify file existence and size
            if os.path.exists(save_path):
                file_size = os.path.getsize(save_path)
                print(f"File exists. Size: {file_size} bytes")

                if file_size == 0:
                    raise ValueError("File was created but is empty")

                # Upload to S3
                raw_url = self.run_context.upload_user_file_to_s3(
                    file_name=filename,
                    original_folder="audio",
                    mime_type="audio/mpeg"
                )
                print(f"generate_speech_file_from_text:Speech saved successfully:Raw_url -> {raw_url}")
                # Get the correct URL
                audio_url = self.run_context.get_file_url(filename, "audio")
                print(f"generate_speech_file_from_text: correct URL -> {audio_url}")

                # Clean up the local file after successful upload
                os.remove(save_path)
                print(f"generate_speech_file_from_text:Local file removed -> {save_path}")

                # Return the URL as a JSON string
                return json.dumps({
                    "content_type": "audio/mpeg",
                    "audio_url": audio_url.get("url")
                })
            else:
                raise FileNotFoundError(f"File does not exist after attempted write: {save_path}")
         except Exception as e:
            error_message = f"Error saving audio file to s3: {str(e)}"
            print(error_message)
            return json.dumps({"error": error_message})
        
    def generate_speech_file_from_text(self, voice: str, text: str) -> str:
        """
        Generate speech from the given text using OpenAI's Text-to-Speech API and save it to a file.

        :param voice: str one of: alloy, echo, fable, onyx, nova, and shimmer
        :param text: str
            The text to be converted to speech.
        :return: str
            The URL of the generated audio file.
        """
        try:
            client = OpenAI(api_key=self.openai_api_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            audio_data = response.content
            print(f"Audio data type: {type(audio_data)}, length: {len(audio_data)} bytes")
            return_str = self._save_audio_to_s3(voice, audio_data)
        except Exception as e:
            error_message = f"Error generating speech: {str(e)}"
            print(error_message)
            return json.dumps({"error": error_message})
        return return_str


    
'''
    def generate_speech_from_text(self, voice: str, text: str) -> str:
        """
        Generate speech from the given text using OpenAI's Text-to-Speech API.
        """
        try:
            client = OpenAI(api_key=self.openai_api_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            audio_data = response.content
            print(f"got audio data")
            # Use a temporary file to safely handle the audio data
            with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmpfile:
                tmpfile.write(audio_data)
                tmpfile_path = tmpfile.name

            # Load and play the audio file safely
            audio_segment = AudioSegment.from_file(tmpfile_path, format="wav")
            play(audio_segment)

            # Clean up the temporary file
            os.remove(tmpfile_path)
            print("Speech has been played successfully.")
        except Exception as e:
            return f"Error generating speech: {str(e)}"
        return "Success converting text to speech"
    
    def generate_speech_from_text(self, voice: str, text: str) -> str:
        """
        Generate speech from the given text using OpenAI's Text-to-Speech API.
        """
        try:
            client = OpenAI(api_key=self.openai_api_key)
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text,
            )
            audio_data = response.content

            # Convert audio data to a NumPy array for playback
            audio_segment = AudioSegment.from_file(BytesIO(audio_data), format="mp3")
            samples = np.array(audio_segment.get_array_of_samples())
            fs = audio_segment.frame_rate

            # Play the audio data
            sd.play(samples, samplerate=fs)
            sd.wait()  # Wait until the audio has finished playing

            print("Speech has been played successfully.")
        except Exception as e:
            return f"Error generating speech: {str(e)}"
        return "Success converting text to speech"
    
'''


