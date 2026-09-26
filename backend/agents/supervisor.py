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
        self.machine.add_transition(trigger='trigger_friday_liquidator', source='*', dest=None, after='on_friday_liquidator')
        
        # Partial Live State Support (Global & Per-Pair Registry)
        self._model_valid_normal = False
        self._model_valid_runner = False
        self._pair_brain_validity = {}

    def set_model_validity(self, normal_valid: bool, runner_valid: bool, symbol: str = None):
        """Mengatur validitas model normal & runner baik secara spesifik pair atau global."""
        if symbol:
            sym = symbol.upper()
            if sym not in self._pair_brain_validity:
                self._pair_brain_validity[sym] = {}
            self._pair_brain_validity[sym]["normal"] = normal_valid
            self._pair_brain_validity[sym]["runner"] = runner_valid
        else:
            self._model_valid_normal = normal_valid
            self._model_valid_runner = runner_valid

    def set_brain_active(self, mode: str, active: bool, symbol: str = None):
        """Mengaktifkan atau menonaktifkan salah satu atau semua otak (normal, runner, all) untuk pair tertentu atau global."""
        target = (mode or "all").lower()
        if active:
            self.force_live_mode(target, symbol=symbol)
        else:
            self.isolate_quarantine(target, symbol=symbol)
        
    def force_live_mode(self, mode: str, symbol: str = None):
        """Manual override from Next.js UI (Forced Live Mode). Bisa 'normal', 'runner', atau 'all', dengan opsional pair symbol."""
        target = (mode or "").lower()
        if symbol:
            sym = symbol.upper()
            if sym not in self._pair_brain_validity:
                self._pair_brain_validity[sym] = {
                    "normal": self._model_valid_normal,
                    "runner": self._model_valid_runner
                }
            if target in ('normal', 'all', 'both'):
                logging.warning(f"[MANUAL OVERRIDE] Otak Normal ({sym}) dipaksa LIVE.")
                self._pair_brain_validity[sym]["normal"] = True
            if target in ('runner', 'all', 'both'):
                logging.warning(f"[MANUAL OVERRIDE] Otak Runner ({sym}) dipaksa LIVE.")
                self._pair_brain_validity[sym]["runner"] = True
        else:
            if target in ('normal', 'all', 'both'):
                logging.warning("[MANUAL OVERRIDE] Otak Normal (Scalp 1:2) dipaksa LIVE.")
                self._model_valid_normal = True
            if target in ('runner', 'all', 'both'):
                logging.warning("[MANUAL OVERRIDE] Otak Runner (Trend 1:5) dipaksa LIVE.")
                self._model_valid_runner = True
            
        if self.state != 'live' and self.is_any_model_valid():
            self.force_start_live()

    def isolate_quarantine(self, mode: str, symbol: str = None):
        """Isolated Circuit Breaker: Mematikan 1 mode atau semua mode tanpa mematikan mesin utama"""
        target = (mode or "").lower()
        if symbol:
            sym = symbol.upper()
            if sym not in self._pair_brain_validity:
                self._pair_brain_validity[sym] = {
                    "normal": self._model_valid_normal,
                    "runner": self._model_valid_runner
                }
            if target in ('normal', 'all', 'both'):
                logging.warning(f"[ISOLATED BREAKER] Otak Normal ({sym}) dinonaktifkan.")
                self._pair_brain_validity[sym]["normal"] = False
            if target in ('runner', 'all', 'both'):
                logging.warning(f"[ISOLATED BREAKER] Otak Runner ({sym}) dinonaktifkan.")
                self._pair_brain_validity[sym]["runner"] = False
        else:
            if target in ('normal', 'all', 'both'):
                logging.warning("[ISOLATED BREAKER] Otak Normal (Scalp 1:2) dinonaktifkan.")
                self._model_valid_normal = False
            if target in ('runner', 'all', 'both'):
                logging.warning("[ISOLATED BREAKER] Otak Runner (Trend 1:5) dinonaktifkan.")
                self._model_valid_runner = False
            
        if not self.is_any_model_valid() and self.state == 'live':
            logging.warning("[SEKRING TOTAL] Semua mode otak mati di seluruh pair. Sistem masuk status Quarantine.")
            self.trigger_max_drawdown()

    def is_any_model_valid(self, symbol: str = None):
        if symbol:
            sym = symbol.upper()
            if sym in self._pair_brain_validity:
                return self._pair_brain_validity[sym].get("normal", False) or self._pair_brain_validity[sym].get("runner", False)
            return self._model_valid_normal or self._model_valid_runner

        if self._model_valid_normal or self._model_valid_runner:
            return True
        for p_state in self._pair_brain_validity.values():
            if p_state.get("normal", False) or p_state.get("runner", False):
                return True
        return False
        
    def is_normal_valid(self, symbol: str = None):
        if symbol:
            sym = symbol.upper()
            if sym in self._pair_brain_validity:
                return self._pair_brain_validity[sym].get("normal", False)
        return self._model_valid_normal
        
    def is_runner_valid(self, symbol: str = None):
        if symbol:
            sym = symbol.upper()
            if sym in self._pair_brain_validity:
                return self._pair_brain_validity[sym].get("runner", False)
        return self._model_valid_runner

    def get_pair_brain_status(self, symbol: str):
        sym = symbol.upper() if symbol else "XAUUSD"
        return {
            "symbol": sym,
            "normal": self.is_normal_valid(sym),
            "runner": self.is_runner_valid(sym),
            "any": self.is_any_model_valid(sym)
        }

    def on_enter_quarantine(self):
        logging.warning("[SEKRING] MAX DRAWDOWN REACHED! System in Quarantine.")

    def on_enter_idle(self):
        logging.info("System is Idle. Waiting for next cycle.")

    def on_friday_liquidator(self):
        logging.info("[SUPERVISOR] Friday Liquidator triggered (1x weekend protection for closed markets). System remains in active state for 24/7 crypto.")

