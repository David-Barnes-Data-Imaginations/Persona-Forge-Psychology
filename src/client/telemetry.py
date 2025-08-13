"""
Simple telemetry manager stub - placeholder for telemetry functionality
"""

class TelemetryManager:
    """Placeholder telemetry manager"""
    
    def __init__(self):
        self.enabled = False
    
    def log_agent_step(self, event):
        """Log an agent step"""
        if self.enabled:
            print(f"📊 Agent step: {event.get('thought', 'No thought')}")
    
    def start_trace(self, name):
        """Start a trace"""
        pass
    
    def end_trace(self):
        """End a trace"""
        pass