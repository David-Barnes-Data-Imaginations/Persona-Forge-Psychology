from smolagents import Tool
"""
class RunCode(Tool):
    name = "RunCode"
    description = "Execute Python code in the E2B sandbox with error handling and safety checks."
    inputs = {
        "code": {"type": "string", "description": "The Python code to execute"}
    }
    output_type = "string"

    def __init__(self, sandbox=None):
        super().__init__()
        self.sandbox = sandbox

    def forward(self, code):
        Execute Python code in sandbox with error handling.
        import os
        
        try:
            # Execute the code in the sandbox
            execution = self.sandbox.run(
                code,
                envs={'HF_TOKEN': os.getenv('HF_TOKEN')}
            )
            
            # Check for execution errors
            if execution.error:
                execution_logs = "\n".join([str(log) for log in execution.logs.stdout])
                error_message = f"EXECUTION ERROR:\n{execution_logs}\n\nTRACEBACK:\n{execution.error.traceback}"
                return error_message
            
            # Return successful execution output
            output = "\n".join([str(log) for log in execution.logs.stdout])
            return output

        except Exception as e:
            error_message = f"TOOL ERROR: {str(type(e).__name__)}: {str(e)}"
            return error_message
"""