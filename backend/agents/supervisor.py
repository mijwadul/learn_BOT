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
        self.machine.add_transition(trigger='start_live', source=['evaluation', 'ingestion'], dest='live', conditions=['is_any_model_valid'])
        self.machine.add_transition(trigger='force_start_live', source='*', dest='live', conditions=['is_any_model_valid'])
        self.machine.add_transition(trigger='fail_evaluation', source='evaluation', dest='research')
        
        # Circuit Breakers
        self.machine.add_transition(trigger='trigger_max_drawdown', source='*', dest='quarantine')
        self.machine.add_transition(trigger='trigger_friday_liquidator', source='*', dest='idle')
        
        # Partial Live State Support
        self._model_valid_normal = False
        self._model_valid_runner = False

    def set_model_validity(self, normal_valid: bool, runner_valid: bool):
        self._model_valid_normal = normal_valid
        self._model_valid_runner = runner_valid
        
    def force_live_mode(self, mode: str):
        """Manual override from Next.js UI (Forced Live Mode)"""
        if mode == 'normal':
            logging.warning("[MANUAL OVERRIDE] Normal Mode dipaksa LIVE.")
            self._model_valid_normal = True
        elif mode == 'runner':
            logging.warning("[MANUAL OVERRIDE] Runner Mode dipaksa LIVE.")
            self._model_valid_runner = True
            
        if self.state != 'live' and self.is_any_model_valid():
            self.force_start_live()

    def isolate_quarantine(self, mode: str):
        """Isolated Circuit Breaker: Mematikan 1 mode tanpa mematikan mesin utama"""
        if mode == 'normal':
            logging.warning("[ISOLATED BREAKER] Normal Mode dihentikan.")
            self._model_valid_normal = False
        elif mode == 'runner':
            logging.warning("[ISOLATED BREAKER] Runner Mode dihentikan.")
            self._model_valid_runner = False
            
        if not self.is_any_model_valid() and self.state == 'live':
            logging.warning("[SEKRING TOTAL] Semua mode mati. Sistem pindah ke Quarantine.")
            self.trigger_max_drawdown()

    def is_any_model_valid(self):
        return self._model_valid_normal or self._model_valid_runner
        
    def is_normal_valid(self):
        return self._model_valid_normal
        
    def is_runner_valid(self):
        return self._model_valid_runner

    def on_enter_quarantine(self):
        logging.warning("[SEKRING] MAX DRAWDOWN REACHED! System in Quarantine.")

    def on_enter_idle(self):
        logging.info("System is Idle. Waiting for next cycle.")
