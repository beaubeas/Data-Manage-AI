import reflex as rx

class PromptHelpers(rx.State, mixin=True):

    #############
    # These are the user_instructions or prompt related functions
    #
    def add_user_instruction(self):
        """ adds a new empty pair to the user instructions on the state model """
        self.app_modified = True
        self.app.prompts.append({"name": "",
                                 "value": "",
                                 "engineering": "", 
                                 "original_prompt": ""})
    
    def set_user_instruction_name(self, name: str, index: int):
        self.app_modified = True
        self.app.prompts[index]["name"] = name

    def set_user_instruction_value(self, instructions: str, index: int):
        self.app_modified = True
        self.app.prompts[index]["value"] = instructions

    def del_user_instruction(self, index: int):
        self.app_modified = True
        # deletes a user instruction on the state model 
        del self.app.prompts[index]

    def moveup_user_instruction(self, index: int):
        self.app_modified = True
        # moves instruction up in the order 
        if index > 0:
            saveit = dict(self.app.prompts[index])
            del self.app.prompts[index]
            self.app.prompts.insert(index-1, saveit)

    def movedown_user_instruction(self, index: int):
        self.app_modified = True
        # moves instruction down in the order
        if index < len(self.app.prompts) - 1:
            saveit = dict(self.app.prompts[index+1])
            del self.app.prompts[index+1]
            self.app.prompts.insert(index, saveit)

    def set_user_instruction_engineering(self, engineering: str, index: int):
        """ This is called when the user choses a new type of prompt engineering"""
        self.app_modified = True
        print(f"Engineering = {engineering}")
        self.app.prompts[index]["engineering"] = engineering
        if engineering == "Original Prompt":
            self.return_to_original(index)

    def set_user_instruction_engineering_arg(self, arg: str, val: str, index: int):
        """ This is called when the user edits an arg of a prompt engineering strategy"""
        self.app_modified = True
        self.app.prompts[index][arg] = val
        


    #############
    # Below are functions for saving the contents of the name and the value boxes for each user instruction
    #
    def edit_user_instruction(self, index: int):
        # goes into edit mode on user instructions maybe do nothing here, or set flag
        print( self.app.prompts[index])

    def save_test_prompt(self):
        # copy test prompt to the agent and save it
        self.toggle_test_prompt_modal()
        return EditorState.save_agent

    def cancel_test_prompt(self):
        # leaving _agent alone will undo any edits
        self.toggle_test_prompt_modal()
        
    def add_test_prompt(self):
        # For async triggers adds a formatted prompt to the chat box for testing
        self.toggle_test_prompt_modal()
        #self.test_prompt = self._agent.test_prompt or ""





    def return_to_original(self, index: int):
        # Check if 'original_prompt' is a key in the dictionary
        if "original_prompt" in self.app.prompts[index]:
            instructions = self.app.prompts[index]["original_prompt"]
            if instructions == "":
                instructions = self.app.prompts[index]["value"]
            else:
                self.app.prompts[index]["value"] = instructions
        else:
            instructions = self.app.prompts[index]["value"]
            self.app.prompts[index]["original_prompt"] = instructions
        self.test_prompt = instructions
        
    def engineer_the_prompt(self, engineering_choice: str, index: int, value: str):
        if engineering_choice == "Chain of thought":
            new_prompt = self.chain_of_thought_engineering(value)
            self.app.prompts[index]["original_prompt"] = value
            self.app.prompts[index]["value"] = new_prompt
            self.test_prompt = new_prompt or ""
        elif engineering_choice == "A U T O M A T":
            new_prompt = self.automat_engineering(index)
            self.app.prompts[index]["value"] = new_prompt
            self.test_prompt = new_prompt or ""
            
    def chain_of_thought_engineering(self, description):
        from supercog.shared.services import config
        from openai import OpenAI
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content":
                 f"These instructions will be used by an AI agent that will access tools as part of its job to execute user instructions. This agent describes the functions these tools provide to the LLM. The LLM  will invoke these functions as needed the results of each function will be provided as context to the LLM. Given that type of processing please convert the instructions that follow into instructions based on the chain of thought methodology. try and summarize each step and allow fpr the LLM to pause at each step which may involve the conclusion of a function call: '{description}'"}
        ]
        client = OpenAI(api_key=config.get_global("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            response_format={ "type": "text" },
        )
        return response.choices[0].message.content
    
    def automat_engineering(self, index):
        """ Construct a prompt from the automat fields """
        prompt = "role: system: content: "+self.app.prompts[index]["Agent Persona"]
        prompt += "role: user: content: "+self.app.prompts[index]["User Persona"]
        prompt += "Undertake the following action: "+self.app.prompts[index]["targeted action"]
        prompt += "Expect output of the form: "+self.app.prompts[index]["output definition"]
        prompt += "Adopt the following style of communication: "+self.app.prompts[index]["mode"]
        prompt += "Specific instructions for atypical cases "+self.app.prompts[index]["atypical cases"]
        prompt += "Spefic topics to adhere to in responses "+self.app.prompts[index]["Topic Whitelisting"]
        return prompt

