from mecom import MeComSerial

class TEC1092:
    """
    Minimal wrapper for Meerstetter TEC-1092 via pyMeCom.
    Read/write functions for temperature and current + PID control.
    """

    # --- Parameter IDs (from MeCom command table) ---
    OBJECT_TEMP_ACTUAL_ID      = 1000  # °C (measured)
    OBJECT_TEMP_SETPOINT_ID    = 3000  # °C (target/setpoint)
    TEC_OUTPUT_CURRENT_ID      = 1020  # A
    TEC_OUTPUT_VOLTAGE_ID      = 1021  # V
    LOOP_STATUS_ID             = 1200  # 0,1,2,...

    # Name used by pyMeCom to toggle loop
    LOOP_ENABLE_NAME           = "Status"

    # Optional mapping for readability
    LOOP_STATUS_CODES = {
        0: "Disabled",
        1: "Enabled (active control)",
        2: "Enabled (error/standby)",
    }

    def __init__(self, port: str, channel: int = 1, autoconnect: bool = True):
        self.port = port
        self.channel = int(channel)
        self.session: MeComSerial | None = None
        self.address = None
        if autoconnect:
            self.connect()

    # --- connection lifecycle ---
    def connect(self):
        if self.session is None:
            self.session = MeComSerial(serialport=self.port)
            self.address = self.session.identify()
        return self.address

    def close(self):
        if self.session is not None:
            try:
                self.session.stop()
            finally:
                self.session = None
                self.address = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # --- low-level helpers ---
    def _ensure(self):
        if self.session is None or self.address is None:
            raise RuntimeError("Not connected. Call connect() first.")

    def _get(self, *, parameter_id=None, parameter_name=None):
        self._ensure()
        kw = dict(address=self.address, parameter_instance=self.channel)
        if parameter_name is not None:
            return self.session.get_parameter(parameter_name=parameter_name, **kw)
        return self.session.get_parameter(parameter_id=parameter_id, **kw)

    def _set(self, value, *, parameter_id=None, parameter_name=None):
        self._ensure()
        kw = dict(value=value, address=self.address, parameter_instance=self.channel)
        if parameter_name is not None:
            return self.session.set_parameter(parameter_name=parameter_name, **kw)
        return self.session.set_parameter(parameter_id=parameter_id, **kw)

    # --- public API: temperature ---
    def read_temperature(self) -> float:
        return float(self._get(parameter_id=self.OBJECT_TEMP_ACTUAL_ID))

    def read_setpoint(self) -> float:
        return float(self._get(parameter_id=self.OBJECT_TEMP_SETPOINT_ID))

    def set_temperature(self, t_celsius: float) -> None:
        self._set(float(t_celsius), parameter_id=self.OBJECT_TEMP_SETPOINT_ID)

    # --- public API: PID loop on/off ---
    def enable_pid(self) -> None:
        # toggle loop using the named parameter
        self._set(1, parameter_name=self.LOOP_ENABLE_NAME)

    def disable_pid(self) -> None:
        self._set(0, parameter_name=self.LOOP_ENABLE_NAME)

    def read_pid_status(self) -> tuple[int, str]:
        code = int(self._get(parameter_id=self.LOOP_STATUS_ID))
        return code, self.LOOP_STATUS_CODES.get(code, f"Unknown ({code})")

    # --- optional extras: electrical readback + convenience ---
    def read_current(self) -> float:
        return float(self._get(parameter_id=self.TEC_OUTPUT_CURRENT_ID))

    def read_voltage(self) -> float:
        return float(self._get(parameter_id=self.TEC_OUTPUT_VOLTAGE_ID))

    def read_all(self) -> dict:
        T    = self.read_temperature()
        Tset = self.read_setpoint()
        I    = self.read_current()
        V    = self.read_voltage()
        code, status = self.read_pid_status()
        return dict(
            T=T, T_set=Tset, I=I, V=V,
            pid_status_code=code, pid_status=status
        )

    def wait_until_stable(self, tolerance: float = 0.05, timeout: float = 300.0, poll: float = 0.5) -> bool:
        """Wait until |T - Tset| <= tolerance. Returns True if reached before timeout."""
        import time
        target = self.read_setpoint()
        deadline = time.time() + timeout
        while time.time() < deadline:
            if abs(self.read_temperature() - target) <= tolerance:
                return True
            time.sleep(poll)
        return False