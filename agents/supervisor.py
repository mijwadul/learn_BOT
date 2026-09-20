from transitions import Machine
import logging

logging.basicConfig(level=logging.INFO)

class SupervisorAgent:
    """
    Agent 0: The Supervisor (Orchestrator & State Machine)
    Mengatur transisi fase operasional (Ingesti Data, Riset, Evaluasi, Live).
    """
    states = ['idle', 'ingestion', 'research', 'evaluation', 'live', 'quarantine']

    def __init__(self):
        self.machine = Machine(model=self, states=SupervisorAgent.states, initial='idle')
        
        # Define transitions
        self.machine.add_transition(trigger='start_ingestion', source='*', dest='ingestion')
        self.machine.add_transition(trigger='start_research', source='ingestion', dest='research')
        self.machine.add_transition(trigger='start_evaluation', source='research', dest='evaluation')
        self.machine.add_transition(trigger='start_live', source=['evaluation', 'ingestion'], dest='live', conditions=['is_model_valid'])
        self.machine.add_transition(trigger='fail_evaluation', source='evaluation', dest='research')
        
        # Circuit Breakers
        self.machine.add_transition(trigger='trigger_max_drawdown', source='*', dest='quarantine')
        self.machine.add_transition(trigger='trigger_friday_liquidator', source='*', dest='idle')
        
        self._model_valid = False

    def set_model_validity(self, valid: bool):
        self._model_valid = valid
        
    def is_model_valid(self):
        return self._model_valid

    def on_enter_quarantine(self):
        logging.warning("[SEKRING] MAX DRAWDOWN REACHED! System in Quarantine.")

    def on_enter_idle(self):
        logging.info("System is Idle. Waiting for next cycle.")
