"""Pure sun position analysis — no Home Assistant dependency.

Extracted from AdaptiveGeneralCover to enable standalone testing and reuse.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd

from ..config_types import CoverConfig
from ..const import DEGREES_IN_CIRCLE
from ..sun import SunData


class SunGeometry:
    """Analyse sun position relative to a window's field of view.

    All inputs are plain data (floats, dataclasses, SunData).
    No Home Assistant imports are needed.
    """

    def __init__(
        self,
        sol_azi: float,
        sol_elev: float,
        sun_data: SunData,
        config: CoverConfig,
        logger: object,
        eval_time: datetime | None = None,
    ) -> None:
        """Initialise with sun position, solar data, cover config, and logger.

        ``eval_time`` is the moment the time-dependent gates (sunset/sunrise
        offset) should be evaluated against. The live pipeline leaves it
        ``None`` so those gates use wall-clock now. The forecast passes the
        timestamp of the sample it is projecting so each point on the
        full-day strip is evaluated at *its own* time rather than the moment
        the forecast happens to be recomputed (issue #516).
        """
        self.sol_azi = sol_azi
        self.sol_elev = sol_elev
        self.sun_data = sun_data
        self.config = config
        self.logger = logger
        self.eval_time = eval_time

    @property
    def azi_min_abs(self) -> int:
        return (self.config.win_azi - self.config.fov_left + DEGREES_IN_CIRCLE) % DEGREES_IN_CIRCLE

    @property
    def azi_max_abs(self) -> int:
        return (self.config.win_azi + self.config.fov_right + DEGREES_IN_CIRCLE) % DEGREES_IN_CIRCLE

    @property
    def gamma(self) -> float:
        return (self.config.win_azi - self.sol_azi + 180) % DEGREES_IN_CIRCLE - 180

    def _elevation_within_bounds(self, elev):
        min_e, max_e = self.config.min_elevation, self.config.max_elevation
        if min_e is None:
            return elev <= max_e
        if max_e is None:
            return elev >= min_e
        return (elev >= min_e) & (elev <= max_e)

    @property
    def valid_elevation(self) -> bool:
        if self.config.min_elevation is None and self.config.max_elevation is None:
            return self.sol_elev >= 0
        within_range = bool(self._elevation_within_bounds(self.sol_elev))
        self.logger.debug("elevation within range? %s", within_range)
        return within_range

    @property
    def valid(self) -> bool:
        azi_min = self.config.fov_left
        azi_max = self.config.fov_right
        valid = bool((self.gamma < azi_min) & (self.gamma > -azi_max) & (self.valid_elevation))
        self.logger.debug("Sun in front of window (ignoring blindspot)? %s", valid)
        return valid

    @property
    def sunset_valid(self) -> bool:
        sunset = self.sun_data.sunset().replace(tzinfo=None)
        sunrise = self.sun_data.sunrise().replace(tzinfo=None)
        ref = self.eval_time.astimezone(UTC) if self.eval_time else datetime.now(UTC)
        now_naive = ref.replace(tzinfo=None)
        after_sunset = now_naive > (sunset + timedelta(minutes=self.config.sunset_off))
        before_sunrise = now_naive < (sunrise + timedelta(minutes=self.config.sunrise_off))
        self.logger.debug("After sunset plus offset? %s", (after_sunset or before_sunrise))
        return after_sunset or before_sunrise

    @property
    def is_sun_in_blind_spot(self) -> bool:
        if (
            self.config.blind_spot_left is not None
            and self.config.blind_spot_right is not None
            and self.config.blind_spot_on
        ):
            left_edge = self.config.fov_left - self.config.blind_spot_left
            right_edge = self.config.fov_left - self.config.blind_spot_right
            blindspot = (self.gamma <= left_edge) & (self.gamma >= right_edge)
            if self.config.blind_spot_elevation is not None:
                blindspot = blindspot & (self.sol_elev <= self.config.blind_spot_elevation)
            self.logger.debug("Is sun in blind spot? %s", blindspot)
            return bool(blindspot)
        return False

    @property
    def direct_sun_valid(self) -> bool:
        result = self.valid and not self.sunset_valid and not self.is_sun_in_blind_spot
        self.logger.debug(
            "direct_sun_valid=%s (valid=%s, sunset_valid=%s, in_blind_spot=%s)",
            result, self.valid, self.sunset_valid, self.is_sun_in_blind_spot,
        )
        return result

    @property
    def control_state_reason(self) -> str:
        if self.direct_sun_valid: return "Direct Sun"
        if self.sunset_valid: return "Default: Sunset Offset"
        if not self.valid:
            if not self.valid_elevation: return "Default: Elevation Limit"
            return "Default: FOV Exit"
        if self.is_sun_in_blind_spot: return "Default: Blind Spot"
        return "Default"

    @property
    def _get_azimuth_edges(self) -> tuple[int, int]:
        return (self.azi_min_abs, self.azi_max_abs)

    def fov(self) -> list[int]:
        return [self.azi_min_abs, self.azi_max_abs]

    def solar_times(self) -> tuple[datetime | None, datetime | None]:
        start, end = self.solar_times_with_position()
        if start is None or end is None: return None, None
        return start[0], end[0]

    def solar_times_with_position(self):
        df_today = pd.DataFrame({"azimuth": self.sun_data.solar_azimuth, "elevation": self.sun_data.solar_elevation})
        solpos = df_today.set_index(self.sun_data.times)
        alpha = solpos["azimuth"]
        elev = solpos["elevation"]
        in_fov = (alpha - self.azi_min_abs) % DEGREES_IN_CIRCLE <= (self.azi_max_abs - self.azi_min_abs) % DEGREES_IN_CIRCLE
        if self.config.min_elevation is None and self.config.max_elevation is None:
            valid_elev = elev > 0
        else:
            valid_elev = self._elevation_within_bounds(elev)
        sunset_utc = self.sun_data.sunset().replace(tzinfo=None)
        sunrise_utc = self.sun_data.sunrise().replace(tzinfo=None)
        offset_sunset = sunset_utc + timedelta(minutes=self.config.sunset_off)
        offset_sunrise = sunrise_utc + timedelta(minutes=self.config.sunrise_off)
        times_utc = solpos.index.tz_convert("UTC").tz_localize(None)
        in_sun_window = (times_utc >= offset_sunrise) & (times_utc <= offset_sunset)
        frame = in_fov & valid_elev & in_sun_window
        rows = solpos[frame]
        if rows.empty: return None, None
        first = rows.iloc[0]
        last = rows.iloc[-1]
        return (
            (rows.index[0].to_pydatetime(), float(first["azimuth"]), float(first["elevation"])),
            (rows.index[-1].to_pydatetime(), float(last["azimuth"]), float(last["elevation"])),
        )
